# Prior art review: Manual J implementations

Review of two public Manual J projects found while searching for Home Assistant or open-source Manual J code. No Home Assistant integration implementing Manual J was found.

Reviewed 2026-11-04 from shallow clones (latest commit only). Nothing was executed.

| Project | Licence | What it is | Detailed note |
|---|---|---|---|
| [SiliconSaga/eldr](https://github.com/SiliconSaga/eldr) | None found (no LICENSE file) | Python Manual J, S and D engine reading Sweet Home 3D models. Demo-grade, not ACCA-certified. | [prior-art-eldr.md](https://github.com/minchinweb/ha-manual-j/blob/master/docs/prior-art-eldr.md) (in Manual J) |
| [Code4Community-Lexington/projects.manual-j](https://github.com/Code4Community-Lexington/projects.manual-j) | GPL-3.0 | Early skeleton: winter-only calculation that does not yet run, a project brief, and a transcribed solar-gain table. | [prior-art-projects-manual-j.md](https://github.com/minchinweb/ha-manual-j/blob/master/docs/prior-art-projects-manual-j.md) (in Manual J) |

## Summary

- **Most useful ideas:** Eldr's attic sol-air term, its effective below-grade U rule, buffer-space precedence, per-surface assembly tags with a category-preserving rule, and its diff and JSON-export conventions. Re-implement the methods; do not copy code, since Eldr has no licence and manual-j is GPL-3.0.
- **Main pitfalls:** the below-grade U is effective (soil included), not the bare wall's; flat solar and attic estimates are crude; Manual S limits in both projects are not ACCA's; manual-j's solar table has nine non-monotone rows and four suspicious duplicated patterns that need checking against the printed source.
- **Not verified:** runtime behaviour of either project, Eldr's test suite, and the source edition of manual-j's table.
