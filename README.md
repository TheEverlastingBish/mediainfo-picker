# mediainfo-picker

Pick which [MediaInfo](https://mediaarea.net/en/MediaInfo) fields to show for a media file, then
copy the output, or the exact `mediainfo` command that produces it.

MediaInfo's text output is either the default set of fields or `--Full`, everything. To show
anything in between you pass `--HideParameter` and `--ShowParameter`, which take internal names
(`General_UniqueID/String`, `Video_Encoded_Library_Settings`) that the normal output never shows.
mediainfo-picker lists every field the file actually has, by its readable label *and* its internal
name, lets you tick the ones you want, and builds the command for you.

Not affiliated with MediaArea.

## What it does

- **Default / Full / Selected fields.** Default is what `mediainfo` shows on its own; Full is
  `--Full`; Selected fields is your own choice, and the only mode in which the field list can be
  changed.
- **Every field the file has**, grouped by section (General, Video, Audio #1, …), with MediaInfo's
  own description as a tooltip. Search filters the list as you type.
- **Apply** shows the output in a monospace box; **Copy output** and **Copy command** put either on
  the clipboard. Pasted into a terminal, the command prints exactly the same text.
- **Your selection is remembered**, in `~/.config/mediainfo-picker/settings.json` on Linux. It is
  stored by field name, so it applies to any file.
- The status bar shows the MediaInfo version in use.

## Requirements

- **MediaInfo's command-line tool**, `mediainfo`, on your `PATH`. It is not bundled. Arch/CachyOS:
  `pacman -S mediainfo`; Debian/Ubuntu: `apt install mediainfo`; macOS: `brew install media-info`.
  Developed against MediaInfoLib v26.10.
- Python 3.10 or later.

## Install and run

```bash
uv tool install git+https://github.com/TheEverlastingBish/mediainfo-picker
mediainfo-picker                 # or: mediainfo-picker /path/to/file.mkv
```

`pipx install git+https://github.com/TheEverlastingBish/mediainfo-picker` works the same way. From
a checkout: `uv run mediainfo-picker`.

## How it decides what to show

- **The fields and their default visibility come from your installed `mediainfo`**, by reading the
  file three times: `--Full`, `--Full --Language=raw` (internal names, line for line) and
  `--Language=raw` (what is shown by default). So they always match your version. The default view
  mostly shows the `/String` variant of a field (`Format/String`, not `Format`), and that is the one
  hidden or shown.
- **Tooltips come from MediaInfoLib's field tables**, bundled in
  `src/mediainfo_picker/data/mediainfo-csv/` from the release tag in `TAG` there. Refresh them with
  `scripts/update-mediainfo-csv.py --tag vXX.YY`.
- **A few fields cannot be hidden by `mediainfo` at all.** `--HideParameter` only accepts names
  listed by `mediainfo --Info-Parameters`, and given any other it prints nothing but an error.
  `Attachments` (in General) is one: it appears in the output but not in that list. Such fields are
  removed from the text after the run instead; the status bar says so, and **Copy command** adds an
  `awk` filter that removes them the same way.

## Development

```bash
uv sync
uv run pytest
```

The tests use `tests/fixtures/`: a one-second synthetic `sample.mkv` and MediaInfo's recorded
output for it (see the README there). Tests that run the real `mediainfo` are skipped when it is not
installed.

## Licence

MIT, see [LICENSE](LICENSE). The bundled MediaInfoLib field tables are © MediaArea.net SARL under
the BSD 2-Clause licence, in [their own LICENSE](src/mediainfo_picker/data/mediainfo-csv/LICENSE).
