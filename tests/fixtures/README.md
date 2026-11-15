# Test fixtures

`sample.mkv` is synthetic: one second of ffmpeg's `testsrc` pattern (x264), two sine tones (AAC),
the title "Sample Title" and an attached `cover.jpg` made from the same pattern. The `.txt` files
are MediaInfoLib v26.10's output for it, recorded from inside this folder so the path is just
`sample.mkv`:

```bash
mediainfo --Full sample.mkv > full.txt
mediainfo --Full --Language=raw sample.mkv > full-raw.txt
mediainfo --Language=raw sample.mkv > default-raw.txt
mediainfo sample.mkv > default.txt
mediainfo --Info-Parameters > info-parameters.txt
```
