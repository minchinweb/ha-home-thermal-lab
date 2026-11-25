# Logo design brief: the Home Assistant suite

Covers the five projects that share one logo family: `ha-house-structure`,
`ha-manual-j`, `ha-home-thermal-lab`, `ha-sunsweep-card` and
`ha-daily-temperature-wave`.

## Home Assistant rules

- Icons: square, 256 px and 512 px (`icon.png`, `icon@2x.png`).
- Logos: landscape, short side 128 px and 256 px. Sun Sweep uses 256 and 512.
- Trimmed: the subject reaches the canvas on its long axis. No padding, borders
  or empty space around the subject.
- PNG only, interlaced. Dark variants are `dark_` prefixed.

## Masters and files

- `brand/icon.svg`, `dark_icon.svg`, `logo.svg`, `dark_logo.svg` are the source.
  Every PNG is rendered from these, never edited by hand.
- The wordmark is an outlined path, never live text.
- Wordmark font: Figtree (variable, SIL OFL), weight 600. The file and its
  licence are in `brand/fonts/` in House Structure, Sun Sweep and Daily
  Temperature Wave.
- Write numbers in path data with no trailing dot. `595. 164.5` ends the path
  early in browsers, which cut the wordmarks short. Format with `rstrip("0")`
  followed by `rstrip(".")`, never `rstrip("0")` alone.

## Wordmark layout

Measured on a 256 px high render:

- Cap height is 0.40 of the logo height. The `H` and `M` of House Structure,
  Manual J and Home Thermal Lab are each 102.4 px tall.
- The wordmark is centred vertically on the logo.
- The gap between the mark's right ink and the wordmark's left ink is 0.203 of
  the logo height (52 px at 256 px). Each logo is trimmed to its own mark, so
  the gap is the same in every logo.
- Marks are left-aligned in their own logo files. In a row of logos, the marks
  right-align against a shared wordmark line, so the wordmarks line up and the
  gap stays at 0.203.

## Palette

The family colours. Shared by all five unless noted.

| Role | Light | Dark |
| --- | --- | --- |
| Outline and wordmark | `#4e342e` brown | `#f4efe6` cream |
| Light fill (house, book) | `#f7f4ef` | `#2b1f1b` |
| Strong accent (swept part) | `#d99a00` gold | `#d99a00` gold |
| Pale accent (day arc) | `#f0d58a` at 55% | `#f0d58a` at 50% |
| Sun | `#e0562b` orange, brown edge | `#e0562b`, cream edge |
| Thermal Lab blue | `#1f77b4` | `#1f77b4` |

## Mark construction

- Sun Sweep: a sun on a house plan, with a heavy ring (34 units on a 512
  master) so it still reads at about 40 px. The wedge is the day's arc, with
  the swept part darker.
- Daily Temperature Wave: a sine wave with a sun dot above it.
- Home Thermal Lab: a sine curve on an axis with three coloured strokes.
- House Structure and Manual J: an isometric house and a book, both in
  warm browns.

## Generators

- `ha-house-structure/scripts/brand.py` draws the house-family brand files with
  Inkscape and optipng. It regenerates all three house integrations unless
  `--only` is given.
- `ha-sunsweep-card/scripts/brand.py` writes the SVG masters and renders the
  PNGs with rsvg-convert and optipng. Run it with
  `uv run --with fonttools python scripts/brand.py`.
- `ha-daily-temperature-wave/scripts/outline_wordmark.py` outlines the wordmark
  in its logo masters. Run it with `uv run --with fonttools python scripts/outline_wordmark.py`.
- Manual J and Home Thermal Lab keep hand-edited masters. Render their PNGs
  from those masters.

## Checks before committing

1. Render each logo at 256 px high with rsvg-convert.
2. Measure the gap between the mark's right ink and the wordmark's left ink.
   It must be 0.203 of the height, within a pixel.
3. Check that the wordmark's cap height is 0.40 of the height.
4. Check the SVG for trailing-dot numbers: `grep -c '[0-9]\. '` must be 0.
5. Check that the shipped PNGs have the logo's aspect ratio and are trimmed.
   The `tests/test_brand.py` check in Sun Sweep covers this.
