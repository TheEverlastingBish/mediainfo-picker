# Changelog

What changed in each release of mediainfo-picker. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (while it is 0.x, a new feature bumps the middle number).

## [0.2.0] - 2026-11-16

First release on PyPI: `uv tool install mediainfo-picker` or `pipx install mediainfo-picker`.

### Added

- A banner with the app's name, and an icon: a white tick on teal.
- A log under the buttons: what happened (opened, applied, copied) and the notes from each run,
  such as fields removed from the text or fields only Full can show.
- **Defaults** and **Clear all** in Selected fields. Both change only the open file's fields, so
  fields saved from other files are kept.
- **Expand all** and **Collapse all**. Clearing a search puts back the sections that were open,
  and opening another file keeps them open.
- Tests on Linux, Windows and macOS, with Python 3.12 and 3.14, on every pull request.

### Changed

- The status bar shows only the versions in use (MediaInfo, Descriptions, MediaInfo Picker) and
  errors.
- The field count sits below the list, and the left panel can no longer be squeezed until it is
  cut off.

## [0.1.0] - 2026-11-15

First version.

### Added

- Default, Full and Selected fields modes; the field list can be changed only in Selected fields.
- Every field the file has, grouped by section, with MediaInfo's own description as a tooltip, and
  a search that filters the list.
- **Apply**, **Copy output** and **Copy command**: the command, pasted into a Unix-style shell,
  prints the same text.
- The selection, mode and window layout are remembered between runs.

[0.2.0]: https://github.com/TheEverlastingBish/mediainfo-picker/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/TheEverlastingBish/mediainfo-picker/tree/v0.1.0
