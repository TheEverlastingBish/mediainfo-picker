#!/usr/bin/env python3
"""Refresh the bundled MediaInfoLib field descriptions from a MediaArea release tag.

    scripts/update-mediainfo-csv.py --tag v26.10

Downloads Source/Resource/Text/Stream/<Kind>.csv for every stream kind, and MediaInfoLib's
LICENSE, from github.com/MediaArea/MediaInfoLib at the given tag, into
src/mediainfo_picker/data/mediainfo-csv/. The tag is recorded in TAG beside them.

The app reads these files only for tooltips. What a field is called and whether mediainfo
shows it by default always come from the installed mediainfo, never from these files.
"""

import argparse
import pathlib
import sys
import urllib.request

KINDS = ["General", "Video", "Audio", "Text", "Other", "Image", "Menu"]
BASE = "https://raw.githubusercontent.com/MediaArea/MediaInfoLib/{tag}/{path}"
DEST = pathlib.Path(__file__).resolve().parent.parent / "src/mediainfo_picker/data/mediainfo-csv"


def fetch(tag: str, path: str) -> bytes:
    with urllib.request.urlopen(BASE.format(tag=tag, path=path), timeout=30) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True, help="MediaInfoLib release tag, e.g. v26.10")
    tag = ap.parse_args().tag
    files = {f"{k}.csv": f"Source/Resource/Text/Stream/{k}.csv" for k in KINDS}
    files["LICENSE"] = "LICENSE"
    got = {name: fetch(tag, path) for name, path in files.items()}  # all or nothing
    DEST.mkdir(parents=True, exist_ok=True)
    for name, data in got.items():
        (DEST / name).write_bytes(data)
    (DEST / "TAG").write_text(tag + "\n")
    print(f"{len(got)} files from MediaInfoLib {tag} -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
