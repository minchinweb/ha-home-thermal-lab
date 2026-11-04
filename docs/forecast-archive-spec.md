# Forecast archive

A proposal for a session to implement. It keeps every room and outdoor forecast the integration issues, in files that the recorder does not purge. Live scoring and the backtest scripts both read them, and the user can clear them. Background: hypothesis 16, section "Forecasting decisions after the literature review", item 4, and the Summary of `docs/literature-review.md`.

## Why

- `ZoneForecastSensor` (`custom_components/home_thermal_lab/sensor.py`) is the only archive of forecasts as issued today. `scoring.issued_from_rows` reads it back from the recorder.
- The recorder purges states after `purge_keep_days` (10 by default). Long-term statistics keep only the state's mean, minimum and maximum, so `predicted_1h`, `predicted_6h` and `start` are lost after the purge. The 24 h path (`points`) is not recorded at all (`_unrecorded_attributes`).
- The outdoor forecast (`_Forecast` in `sensor.py`, Open-Meteo, fetched at most hourly) is not kept anywhere. The backtests therefore use measured weather in place of a forecast.
- Hypothesis 16's next steps all need weeks of issued forecasts: a fallback to D that depends on the score, error bands, the season-transition test, and a comparison of weather models for Edmonton.

## Not in scope

- Changing the forecast method, the model or the score definitions. The archive records what the integration already computes, plus D's leads (below).
- The Open-Meteo previous-runs backfill. That is a separate script, described at the end as a follow-up.

## Storage

- Directory: `hass.config.path("home_thermal_lab", "archive")`, created on first write.
- Files: JSON Lines, one per kind and UTC month, for example `room-2026-11.jsonl` and `outdoor-2026-11.jsonl`. Gzip a month once it is two months old: `room-2026-09.jsonl.gz`. The reader handles both.
- Do not use Home Assistant's `Store`. It rewrites the whole file on every save, and this file only grows.
- Every file operation runs in the executor (`hass.async_add_executor_job`), never in the event loop.
- Every line has `"v": 1` (a schema version), `"kind"` and `"at"`. `"at"` is the issue time as an ISO 8601 UTC instant with a `Z` or `+00:00` offset. The reader parses instants and never compares timestamp text.
- A missing value is JSON `null`, never 0 (see the literature review's first pitfall).

## Records

### `room`: one line per zone per issue (every `SCAN_INTERVAL`, 15 minutes)

| Field | Meaning |
|---|---|
| `v`, `kind`, `at` | as above; `kind` is `"room"` |
| `zone` | the forecast sensor's entity id (the stable key; the name goes in `name`) |
| `name` | the zone's friendly name at issue time |
| `method` | what was issued: `"hybrid"`, `"profile"` and so on, as in the sensor's `method` attribute |
| `fallback` | why D was issued instead of H (`null` if H was issued), for example `"no usable fit"`, `"score"` |
| `start` | the room temperature at issue (°C) |
| `setpoint` | the setpoint at issue (°C, `null` if none) |
| `program` | `"yesterday"` (the assumed setpoint program; the rule as a name, not the 96 values) |
| `outdoor_at` | the `at` of the outdoor record this forecast used, so the two can be joined |
| `outdoor_shift` | the outdoor correction applied (°C) |
| `fit_at` | when the zone's model was last fitted (UTC instant, `null` if none) |
| `params` | the fitted parameters used (`a`, `b`, `n`, `x`, `c`, `g`, `w`, `h`, `e`, `y`, `f`; absent terms `null`) |
| `neighbours` | the neighbour zones used |
| `leads` | `{"1": t, "3": t, "6": t}`: the issued prediction (°C) at each lead in hours |
| `leads_d` | the same leads from the profile with offset (D), computed whether or not D was issued |
| `path` | the full 24 h path as `[[minutes_ahead, t], …]` at 15-minute steps, written **only on the first issue of each UTC hour** (otherwise absent) |

The sensor must compute D's leads on every issue for `leads_d`. This is new work: the sensor needs it so the score-based fallback (hypothesis 16, item 2) can compare the two methods live.

### `outdoor`: one line per successful Open-Meteo fetch

| Field | Meaning |
|---|---|
| `v`, `kind`, `at` | `kind` is `"outdoor"`; `at` is the fetch time |
| `source` | `"open-meteo"` |
| `model` | the Open-Meteo `models` parameter used (`"best_match"` today; record it so a model change splits the scores) |
| `lat`, `lon` | as sent |
| `bias` | the bias against the outdoor sensor at fetch time (°C, `null` if not enough data), and `bias_hours` |
| `hours` | `[[hour_end_utc, temperature, dni, diffuse, cloud], …]` for the forecast hours only (not the `past_days` hours) |

`bias` is the bias from the last learning pass (every six hours), not recomputed at the fetch. A failed fetch writes nothing. The room records' `outdoor_at` then points to the last good fetch, which is the truth.

### Size

Assume 4 zones and 96 issues a day, with about 0.4 kB per room line without the path and 1.5 kB with it (24 lines per zone a day). That is about 0.3 MB a day, or 110 MB a year uncompressed, and 15 to 25 MB once gzipped. The outdoor file is about 24 lines a day of 2 kB. Measure the real sizes in the first week and record them here.

## Module: `archive.py`

Standard library only, so it can be tested without Home Assistant (like `scoring.py` and `options.py`).

```python
SCHEMA = 1

def append(directory: Path, record: dict) -> None
    # validates kind/at/v, picks the month file from record["at"],
    # serialises with json.dumps(allow_nan=False) and appends one line + "\n",
    # opening in "a" mode with newline="\n" (no CRLF on Windows).

def read(directory: Path, kind: str, start: datetime, end: datetime,
         zone: str | None = None) -> Iterator[dict]
    # reads only the month files that overlap [start, end), plain or .gz,
    # yields records in file order with start <= at < end.
    # A malformed line is skipped and counted (see `stats`), never raised.

def compress_old(directory: Path, now: datetime, keep_plain_months: int = 2) -> list[Path]

def stats(directory: Path) -> dict
    # per kind and month: lines, bytes, malformed lines, first and last `at`, zones.

def clear(directory: Path, *, kinds=None, zones=None, before=None,
          dry_run=True) -> dict
    # see Clean-up below.
```

- **Duplicates:** the writer skips a record whose `(kind, zone, at)` equals the last one it wrote for that zone. That is the restart-at-the-boundary case. The reader also de-duplicates on `(kind, zone, at)` parsed as an instant. Decide what counts as new once, at the writer, as the review recommends, and treat the reader's de-duplication as a safeguard. Count every duplicate it drops.
- **Partial last line** (a crash mid-write): the reader skips it and counts it as malformed. The writer starts its next append with `"\n"` if the file does not end in one.
- **Concurrency:** Home Assistant has one writer per file, through one executor call at a time per file. Hold an `asyncio.Lock` per directory in the integration, not in `archive.py`.

## Wiring

- **`ZoneForecastSensor._refresh`:** after the forecast is built, append the `room` record. Include `path` when this is the first issue in the current UTC hour, and keep that hour in the sensor. An append failure is logged at warning level, once an hour, and counted in an `archive_errors` attribute. It never stops the sensor.
- **`_Forecast.hours`:** after a successful fetch, append the `outdoor` record. Its `at` is what the room records put in `outdoor_at`, so `_Forecast` needs to expose its `_fetched` time.
- **`scoring.score`:** take issued forecasts from `archive.read(kind="room")` for the `SCORE_DAYS` window. Fall back to `issued_from_rows` (the recorder) only for the part of the window before the archive's first record, and say in the sensor's attributes which source was used (`scored_from: "archive" | "recorder" | "both"`). Score D's leads the same way, as `error_d_1h` and so on.
- **Daily housekeeping:** once a day, run `compress_old` and the retention rule below in the executor.
- **`scripts/predict_rc.py`:** add `--archive PATH`, pointing at a copy of the archive directory (or a mounted share). Read issued outdoor forecasts through `archive.read` instead of measured weather when it is given.

## Clean-up

The user must be able to remove what the archive holds: all of it, one zone, one kind, or everything before a date.

1. **Service `home_thermal_lab.clear_archive`**, registered in `async_setup_entry` once per Home Assistant instance, not once per entry. Add `services.yaml` and translations. Fields:
   - `kinds` (optional, list of `room` and `outdoor`; default both)
   - `zones` (optional, list of forecast sensor entity ids; default all; only applies to `room`)
   - `before` (optional date; default everything)
   - `dry_run` (boolean, **default true**)

   It returns a response (`SupportsResponse.OPTIONAL`): files and lines that would be or were removed, and bytes freed. Reject unknown kinds, unknown zones and a `before` in the future with `ServiceValidationError`. Never treat a filter that matches nothing as "everything" (review pitfall: a missing scope must fail closed).
2. **How `clear` removes lines:** a whole month file that the filter fully covers is deleted. Otherwise the file is rewritten without the matching lines, to a temporary file in the same directory followed by `os.replace`, so a crash leaves either the old or the new file. Gzipped months are rewritten as gzip. A dry run reads only.
3. **Retention option:** add `archive_keep_days` to the options flow (integer, 0 = keep everything, default 0). Daily housekeeping applies it as `clear(before=today - keep_days, dry_run=False)`, and logs what it removed at info level.
4. **Removing the integration:** `async_remove_entry` for the *last* config entry does **not** delete the archive, because the data cannot be rebuilt. It logs where the archive is and that `clear_archive` (run before removal) or deleting the directory removes it. Say the same in the README.
5. **Panel / diagnostics:** expose `archive.stats` in the integration's diagnostics download, so the user can see what is stored before clearing it.

## Tests (`tests/test_archive.py`, standard library and `tmp_path`)

- Append and read back a `room` and an `outdoor` record, and check that `null` survives as `None` and that no NaN can be written.
- Two records either side of a month boundary (UTC) land in two files, and a read spanning the boundary returns both in order.
- A duplicate `(kind, zone, at)` is skipped by the writer. Two strings for the same instant (`Z` and `+00:00`) are one record to the reader.
- A truncated last line is skipped and counted. The next append still produces valid lines.
- `compress_old` gzips the right months, and `read` returns the same records before and after.
- `clear`:
  - dry run changes nothing and reports the right counts
  - clearing by zone leaves other zones' lines and outdoor records
  - `before` removes whole earlier months by deletion and splits the boundary month by rewrite
  - an unknown zone is an error, not "all"
- `scoring` with archived records: a lead that is `null` is skipped, not scored as zero error, and D's leads are scored under their own keys.
- A test that the room record's fields match the sensor's attributes for the shared names, so the two cannot drift.

## Follow-up (separate task): backfill issued outdoor forecasts

A script, `scripts/backfill_outdoor.py`, would pull past issued forecasts for the house from Open-Meteo's previous-runs or historical-forecast API. It writes them as `outdoor` records with `"source": "open-meteo-previous-runs"` and `"backfilled": true`. First check that the API serves our location (Edmonton) and variables at hourly resolution, and how its "previous day N" lead maps to our issue times. Use the backfill to compare `best_match` against the Canadian GEM/HRDPS models in `predict_rc.py`.

## Done when

- Both record kinds are written live and survive a recorder purge.
- The forecast sensor scores from the archive and reports `scored_from`, H's errors and D's errors.
- `clear_archive` works with a dry run, by zone, by kind and by date, and the retention option works.
- The README documents the archive's location, size and clean-up.
- `invoke test` and `invoke lint` pass.
