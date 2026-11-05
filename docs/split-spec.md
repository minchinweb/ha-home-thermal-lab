# Splitting the lab into three integrations

Home Thermal Lab has grown three jobs: describing the house, sizing its
heating and cooling (Manual J, S and D), and the experiments that learn how
the house behaves and forecast its thermostats. This spec splits them into
three integrations. Nothing here is built yet.

| Integration | Repo | Domain | Job |
| --- | --- | --- | --- |
| House Structure | `ha-house-structure` (exists) | `house_structure` | The house and its parts, drawing it, and the **Thermal Lab** sidebar page that the other two add tabs to |
| Manual J | `ha-manual-j` (new) | `manual_j` | Manual J, S and D: static loads from the house, the design weather and the equipment |
| Home Thermal Lab | `ha-home-thermal-lab` (this one) | `home_thermal_lab` | Experiments, fitted models, shadow zones, forecasts, energy sensors |

Dependencies run one way, with one optional back-reference:

```
House Structure  <--  Manual J  <--(optional)--  Home Thermal Lab
       ^                                                      |
       +------------------------------------------------------+
```

Manual J and Thermal Lab both list `house_structure` under `dependencies` in
their `manifest.json`. Home Assistant then won't set either of them up unless
House Structure is installed, and always sets House Structure up first, so
its rooms are published before they're needed. Neither works on its own:

- Manual J has no input without House Structure. The rooms, walls, windows,
  ducts, equipment and buildings are what it calculates from.
- Thermal Lab could keep working from settings typed on each zone, as it does
  today. But once rotation and roofs live only in House Structure (below),
  typed window faces have no house to turn by. Keeping the fallback would mean
  keeping a second copy of the house in the lab, which is what this split is
  meant to remove. So the fallback goes: a zone is a room (area) in House
  Structure.

Manual J *reads* Thermal Lab's fitted cooling rates when Thermal Lab is
installed, to fill the "UA fitted" and "Fitted ÷ calc" columns, and leaves
them empty when it isn't. That's why it's `after_dependencies`, not a
dependency. No integration imports another's Python. They share data through
`hass.data`, as House Structure and the lab already do.

## The Thermal Lab page (House Structure)

House Structure registers the sidebar panel. Its title is **Thermal Lab** and
its URL is `/thermal-lab`. The page is a frame: a heading, a tab bar across the
top, and an iframe that shows the chosen tab. Each tab is a page that its own
integration serves, so each integration ships its own HTML and its own
websocket commands, and can be released on its own. Chart.js is shared
(below).

### Registering a tab (the plugin contract)

An integration adds a tab by putting an entry in
`hass.data["house_structure_tabs"]`. It doesn't have to import House
Structure or wait for it to load:

```python
tabs = hass.data.setdefault("house_structure_tabs", {})
tabs["hvac_design"] = {
    "title": "HVAC design",
    "url": "/manual_j_static/index.html?v=<hash>",
    "order": 20,
}
hass.bus.async_fire("house_structure_tabs_updated")
```

It removes the entry, and fires the event again, when it unloads.

- `title`: the tab's label.
- `url`: the page to show in the iframe. A cache-busting `?v=` is up to the
  integration.
- `order`: where the tab goes, from low to high. House Structure's own tab is
  10, Manual J is 20, Thermal Lab's tabs start at 30.

The frame lists the tabs over its websocket command
`house_structure/tabs` (a list of `{key, title, url, order}`, in order). It
also subscribes to `house_structure_tabs_updated`, so a tab appears or goes
away without a reload. It remembers the chosen tab in `localStorage` and in
the URL hash (`/thermal-lab#hvac_design`), so a tab can be linked to.

### What a tab page gets

A tab page sits two iframes deep (the panel, then the frame), so it can't use
`window.parent.hassConnection` as the lab's page does today. The frame
re-exports what it gets from Home Assistant:

- `window.hassConnection`: the frame sets it to its parent's, so a tab page
  still uses `parent.hassConnection` and asks over Home Assistant's own
  websocket, with no separate login.
- Theme: a tab page reads Home Assistant's CSS variables and dark mode from
  `window.top.document` rather than `window.parent.document`. The frame keeps
  no theme of its own.

`frontend/tab.js` in House Structure holds these two helpers (connection and
theme), so a tab page can load it from `/house_structure_static/tab.js`
instead of copying it.

### Chart.js, shipped once

House Structure vendors Chart.js. The lab already does this:
`chart.umd.min.js`, pinned in `vendor.json`, refreshed with `invoke vendor`,
checked by `test_vendor.py`. All of it moves to House Structure, which serves
the file at `/house_structure_static/chart.umd.min.js` with long cache
headers. Tab pages load it from there, and the lab and Manual J don't carry a
copy. Both depend on House Structure, so the file is always there. One pinned
version means one place to upgrade it, and a Chart.js upgrade is a House
Structure release that the other tabs must keep working with.

### House Structure's own tab: House

Order 10. It draws the whole house, with its rooms put together in place, and
a picker to show one room on its own (`room.svg`, as now). It also lists the
equipment parts (below).

The house is drawn as layers that can be switched on and off with chips over
the drawing. The choice is remembered in `localStorage`:

| Layer | From | Default |
| --- | --- | --- |
| Rooms (walls, roofs, windows, doors) | House Structure | always on |
| Heating runs (registers and their ducts) | House Structure | on |
| Roofs (each roof's slope, gables) | House Structure | off |
| Heat flow (lab overlay) | Thermal Lab, when installed | off |

Apart from the layers, a **Floors: Together / Apart** toggle draws the floors
apart, each lifted 2.5 m more than the one below, so an upper floor doesn't
hide the one under it (`plan.svg?exploded=1`; done in `80d5edd`). The
heating runs are drawn to the lifted floors but measured on the real ones.
The anchors are worked out after the lift, so overlays follow the floors.

To make that possible, `house_svg` (in `drawing.py`) changes in two ways. The
page fetches `plan.svg` as text and puts it inline, not in an `<img>`, so it
can reach inside the drawing.

- **Layer groups**: each layer is a `<g data-layer="rooms">`,
  `<g data-layer="runs">`, and so on. The page hides a layer by toggling a
  class, without fetching the drawing again.
- **Anchors**: an empty `<g data-layer="anchors">` holds points the drawing
  already works out but doesn't keep:
  - `data-room` (area id): each room's projected floor centre;
  - `data-between="<area>|<area>"`: the middle of each wall two rooms share
    (`_shared_face`);
  - `data-outside="<area>|<face>"`: the middle of each outside face;
  - `data-register` (part id): each register's outlet.

  These are in the drawing's own pixel space, so an overlay can draw arrows
  and labels at them without knowing about the projection.

### Overlays (the second plugin contract)

An overlay is registered the same way a tab is, in
`hass.data["house_structure_overlays"]`, followed by the event
`house_structure_overlays_updated`:

```python
overlays = hass.data.setdefault("house_structure_overlays", {})
overlays["heat_flow"] = {
    "title": "Heat flow",
    "command": "home_thermal_lab/heat_flow",  # a websocket command
    "refresh_s": 60,
}
```

Values are watts, positive into a room: `between` is positive from `from`
to `to`, and `outside` is positive coming in. A `heating` value may name its
`register` (a House Structure part id); otherwise it's shared out over the
room's outlets. The House tab shows a chip for each registered overlay. When a chip is on,
the tab calls the overlay's websocket command, again every `refresh_s`, and
draws what comes back at the anchors. The command answers with flows in
watts, all optional:

```json
{
  "as_of": "2026-11-04T21:00:00Z",
  "between": [{"from": "kitchen", "to": "office", "w": 85.0}],
  "outside": [{"room": "office", "face": "N", "w": -140.0}],
  "heating": [{"room": "office", "w": 420.0}],
  "solar": [{"room": "office", "w": 60.0}],
  "notes": ["Z3 has no fitted model yet."]
}
```

House Structure draws these, so every overlay looks alike:
- an arrow across each shared wall, pointing the way heat moves, sized by its
  watts and labelled with them;
- an arrow at each outside face;
- a flame at the register for `heating`;
- a sun at the room centre for `solar`;
- the `notes` under the drawing.

House Structure draws whatever an overlay sends. It doesn't need to know what
the flows mean.

## House Structure: new parts

Three new sub-entry types. They are parts of the house, and both Manual J and
the lab read them.

- **Furnace**: the room it's in (area), stage inputs in BTU/h (high, and low if
  it has two stages), AFUE (%), and the blower curve (the text
  `parse_blower` reads today). Moved from the lab's energy sub-entry.
- **Air conditioner**: capacity in tons, sensible capacity in BTU/h
  (optional). Moved from the lab's energy sub-entry.
- **Building**: a detached building (a garage, say): its name and its areas.
  Moved from the lab's building sub-entry. Its setpoints go to Manual J
  (below), since they're design conditions, not part of the building.

`publish_rooms` adds them to the summary: `hass.data["house_structure"]` gets
`"equipment": {"furnaces": [...], "air_conditioners": [...]}` and
`"buildings": [...]`. They're lists, so a house with two furnaces can say so.
The summary stays at version 1, because keys were only added: the lab checks
for exactly version 1, so bumping it would have broken the lab for nothing.
They show on the House tab and on Manual J's HVAC design tab.

## Repairs only when something needs the number

House Structure used to raise a repair for every wall or roof without a size,
and every room without a floor area. Its own sensors don't use those numbers,
though, so the repair was only right when another integration did. Now each
integration says what it uses, and a missing size raises a repair only if
something needs it. The repair names who needs it:

```python
needs = hass.data.setdefault("house_structure_needs", {})
needs["manual_j"] = {
    "title": "Manual J",
    "needs": ["wall_size", "roof_size", "room_floor"],
}
hass.bus.async_fire("house_structure_needs_updated")
```

An integration removes its entry, and fires the event again, when it unloads.

- Manual J needs `wall_size`, `roof_size` and `room_floor`.
- The lab needs `room_floor` for a room's heat capacity.

Any other warning about the house should follow the same rule: it goes in the
integration that needs the number, or is raised by House Structure only when
something has said it needs it.

## Manual J

A new integration and repo, set up to the Python style guide (run
`python-style:audit` when creating it).

Moves from this repo, with their tests:

- `manual.py`, split so each manual is its own file. Each file uses the
  standard library only, so all of them are tested without Home Assistant.
  The split follows the sections already in `manual.py`:
  - `air.py`: air properties and units (`rho_cp`, `air_density`, `inches`,
    `btu_h`, …).
  - `building.py`: `Surface`, `Room`, `Design`, the design temperatures from
    the record, humidity, and the envelope from measurement (`room_capacity`,
    `ua_from_rate`, `envelope_scale`, window U-values).
  - `manual_j.py`: room loads (`heating_load`, `cooling_load`,
    `room_airflow`, `room_load`, `RoomLoad`).
  - `manual_s.py`: equipment (`Furnace`, `AirConditioner`, `check_heating`,
    `check_cooling`).
  - `manual_d.py`: ducts (`Segment`, `Run`, `evaluate_run`,
    `round_size_for_friction`, `available_static`).
  - `project.py`: `Project` and `calculate`, which run J, then S, then D.

  `test_manual.py` splits the same way: `test_manual_j.py`,
  `test_manual_s.py`, `test_manual_d.py` and `test_project.py`.
- `house_model.py` (the project from House Structure's summary) and
  `test_house_model.py`
- `loads.py` (design conditions from the record, equipment, `assemble_all`)
  and `test_loads.py`
- From `panel.py`: `ws_loads`, `_hourly_outdoor` and its hourly cache,
  `_buildings`, `_energy_settings`, `_house_settings`, `_rates`
- From `frontend/index.html`: the Loads view, which becomes the **HVAC design**
  tab's page
- `docs/prior-art-eldr.md`, `docs/prior-art-projects-manual-j.md`, and the
  Manual J parts of `docs/house-structure-duct-spec.md`

Its own settings (one config entry, no sub-entries):

- **Outdoor temperature sensor**: the recorded record the design temperatures
  come from (two years of hourly means, as now). This is its only live input.
  Without it, the assumed design conditions are used, as today.
- **Envelope defaults**: `infiltration_ach`, `wall_r`, `roof_r`, `door_r` and
  `basement_floor_r` (`ENVELOPE_SETTINGS`), moved from the lab's integration
  settings.
- **Building setpoints**: the indoor heating and cooling design temperatures
  for each House Structure building, keyed by the building's name. They're
  moved from the lab's building sub-entry. A building with none set uses the
  house's.

It reads from House Structure the rooms, ducts, equipment and buildings, and
reloads its results on `house_structure_updated`. It registers its needs
(above), so a wall without a size raises a repair only once Manual J is
installed. It reads Thermal Lab's
fitted rates if they're there (below). Its websocket command is
`manual_j/loads`.

## Home Thermal Lab after the split

- Stops registering its own sidebar panel. Registers the **Zones** tab
  (order 30) instead, with the zone view of `frontend/index.html`. Later lab
  views become more tabs (31, 32, …) or views inside Zones.
- Publishes each zone's fitted cooling rate for Manual J:
  `hass.data["home_thermal_lab_fitted"] = {area_id: {"a": per_hour}}`, updated
  when a fit changes, with the event `home_thermal_lab_fitted_updated`. This
  takes the place of `panel._rates`.
- Registers the **Heat flow** overlay on the House tab (above), through its
  command `home_thermal_lab/heat_flow`. Each value is for the current hour:
  - `between`: each internal wall's temperature difference (House Structure's
    sensor) times its conductance. The conductance is the wall's area times
    its U-value (Manual J's nominal for an internal wall) to start with, and
    the fitted crossover rate where hypothesis 06/10 has one.
  - `outside`: each room's outside faces, from the zone's fitted loss `a`
    shared out over the faces by area.
  - `heating`: the zone's learned heating rate `h` while its register is
    calling, shared out over the zone's registers.
  - `solar`: the zone's fitted solar term `g` times the sun on its windows. It
    is the gain the model credits the room with. House Structure's own window
    sensors give the glass's figure. The overlay notes both when they differ
    by more than half.

  A room with no fitted zone gets no values, and a note says so.
- Drops the envelope settings from its integration settings, the nameplate
  fields (`afue`, `blower_curve`, `cool_tons`, `ac_sensible_btuh`, `area_id`)
  from the energy sub-entry, and the building sub-entry. The energy sensors
  keep their per-state powers (`kw`), which are what they model.
- Drops the house rotation and roofs from its integration settings, along
  with its own `orientation.py`, `map_view.py`, the roof parsing in
  `options.py` and the outline drawing on its settings form. House Structure
  already measures the rotation from OpenStreetMap and has roof parts, so
  only one copy is left.
- Depends on House Structure (above). Each zone, contribution chart and
  call-statistics sensor takes its room from House Structure: the
  thermostat, room sensor, windows, roofs, sunlit walls and below-ground
  setting. Settings typed on the zone that only stood in for the room (window
  faces, sunlit walls, per-zone rotation) are removed. Overrides that are
  about the experiment rather than the house (a pinned model, the target
  wave, the deadband) stay. YAML zones need an `area_id`.

## Moving existing settings

There's one house, so a one-off move by hand is enough: type the furnace, AC
and garage into House Structure, and the envelope defaults and garage
setpoints into Manual J, before upgrading the lab. Check that House
Structure's rotation and roofs match the lab's, and that every zone has a
room. Diagnostics from the lab before the upgrade keep a
copy of the old values. The lab's config entry migration then removes the old
keys.

## Order of work

Each step leaves all three working.

1. **House Structure**, in two commits:
   - **Done** (`3fdb2b8` on `thermal-lab-panel`): the frame page,
     `house_structure/tabs` (a subscription), `tab.js`, Chart.js and its
     vendoring, a first House tab (the drawing as an image, a room picker,
     the equipment and buildings), the Furnace, Air conditioner and Building
     parts in the summary, and repairs on need. `frontend` is an
     after-dependency, not a dependency: registering an iframe panel doesn't
     need the frontend set up, and the tests don't have its package.
   - **Done** (`80d5edd`, `65582f2`, `362621c`): floors apart or together
     (a room within 3 1/2 ft of a floor stays on it), quarter-turn views,
     the layers (rooms, runs, roofs), the roofs drawn as slopes and gables,
     the anchors, and the overlay contract with its drawing on the House tab.
     Checked with a local preview of the tab, using sample data and
     screenshots, not yet in a real Home Assistant.

   The lab still has its own sidebar entry and its own Chart.js, so for now
   there are two of each.
2. **Manual J**: the new repo with the moved code and tests, its
   settings, and the HVAC design tab. Its fitted columns stay empty until step
   3 publishes the rates. The lab's own Loads view keeps working alongside it.
   **Done** (`5735ae6` in `ha-manual-j`), with these differences from the plan
   above:
   - The air, building and design-temperature tests are in their own
     `test_building.py`, beside the four test files named above.
   - A building's setpoints are set on Reconfigure: a menu offers the settings
     or a building, chosen from House Structure's buildings. Clearing both
     setpoints puts the building back on the house's.
   - With more than one furnace or air conditioner, the first is checked and
     the rest are noted.
   - The numbers are worked out on each request, so they follow House
     Structure without listening for `house_structure_updated`; only the
     outdoor record is kept, until the hour changes.
   - Checked with a local preview of the tab using sample results, not yet in
     a real Home Assistant.
3. **Home Thermal Lab**: register the Zones tab and drop the old panel and its
   Chart.js, publish the fitted rates, add the Heat flow overlay, remove the moved code, settings and tests, and update the
   README, CHANGELOG and hypotheses that point at the Loads tab.
   **Done** (on `split-plan`, merged to `master`), with these differences
   from the plan above:
   - `between` uses each room's temperature sensor from House Structure's
     summary, which is what its internal-wall sensor subtracts, rather than
     looking that sensor up. The nominal conductance is 2.0 W/m²K across a
     wall and 1.4 through a floor (`heat_flow.py`); Manual J has no internal
     U-value, since an internal wall isn't a loss there.
   - The fitted crossover is the zone's `n` (coupling to the mean of its
     neighbouring zones), shared over the room's inside walls and floors by
     area; with both rooms fitted, the mean of the two.
   - Fitted rates become watts through the room's air heat capacity, as
     Manual J's "UA fitted" column does, so the watts compare rooms rather
     than match a meter. A note on the overlay says so.
   - The old settings are removed by the config entry's migration (minor
     version 2, `migrate.py`), which logs a warning naming each one.
     YAML energy sensors still accept `area_id`, and ignore it.
   - The manifest drops `frontend` from its dependencies, as nothing
     registers a panel now. `house_structure` stays an after-dependency
     until step 4, which makes it a dependency.
   - Checked with tests against Home Assistant 2026.10 (the tab, the
     overlay's command, the fitted rates and the migration), not yet in a
     real Home Assistant.
4. **Home Thermal Lab, rotation and roofs**: add the `house_structure`
   dependency, read rotation and roofs from House Structure, and remove the
   lab's copies and the zone-typed fallback. This is its own step because it
   touches the fitting code (`learn.py`, `sensor.py`, `options.py`), not just
   the panel.
   **Done** (on `split-plan`, merged to `master`), with these differences
   from the plan above:
   - `learn.py` needed no change: the fit already worked from the light on
     the zone's planes. Only `sensor.py`'s light on the windows and walls
     changed, to House Structure's planes alone, which are already turned by
     its rotation. `irradiance.light_on_surfaces` (faces and a rotation) stays
     for the scripts.
   - The house-wide `shade_below` went too: each of House Structure's parts
     has its own.
   - The thermostat and room sensor can still be picked on a zone, and win
     over the room's, since they choose an entity rather than describe the
     house. `below_ground` is always the room's. The ground wave and a zone's
     `ground_entity` stay in the lab.
   - Heating-call statistics still work from a thermostat alone; with a room,
     the thermostat comes from its register.
   - A zone or contribution whose area has no room in House Structure is
     skipped, with an error in the log. YAML zones and contributions are
     checked once their room is filled in, so a YAML error shows in the log
     rather than in the configuration check.
   - The config entry's migration (minor version 3) removes the house's
     `rotation`, `roofs` and `shade_below`, and each zone's and
     contribution's `windows`, `sunlit_walls`, `roofs`, `rotation`,
     `shade_below` and `below_ground`, logging a warning naming each, and
     warns about a zone with no room.
   - `scripts/house_orientation.py` went with `orientation.py`.
   - The tests stand a mock `house_structure` integration in for the real
     one (`tests/conftest.py`). Checked with tests against Home Assistant
     2026.10, not yet in a real Home Assistant.
