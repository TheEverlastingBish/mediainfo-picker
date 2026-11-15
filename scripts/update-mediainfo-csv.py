#!/usr/bin/env python3
"""Refresh the bundled MediaInfoLib field descriptions from a MediaArea release tag.

Example usage:

    uv run scripts/update-mediainfo-csv.py               # the installed mediainfo's version
    uv run scripts/update-mediainfo-csv.py --tag v26.10  # a given release

Downloads Source/Resource/Text/Stream/<Kind>.csv for every stream kind, and MediaInfoLib's licence
as LICENSE-MediaInfoLib, from github.com/MediaArea/MediaInfoLib at the tag, into
src/mediainfo_picker/data/mediainfo-csv/, and records the tag in TAG there. The kinds are the ones
the installed mediainfo lists in `--Info-Parameters`, so a kind added in a later release is fetched
without changing this script. Tables for kinds it no longer lists are removed.

The app reads these files only for tooltips. What a field is called and whether mediainfo shows it
by default always come from the installed mediainfo, never from these files.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import urllib.request

from mediainfo_picker.engine import MediaInfo

BASE = "https://raw.githubusercontent.com/MediaArea/MediaInfoLib/{tag}/{path}"
DEST = pathlib.Path(__file__).resolve().parent.parent / "src/mediainfo_picker/data/mediainfo-csv"


def fetch(tag: str, path: str) -> bytes:
    with urllib.request.urlopen(BASE.format(tag=tag, path=path), timeout=30) as resp:
        data: bytes = resp.read()
        return data


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--tag", help="MediaInfoLib release tag, e.g. v26.10 (default: the installed mediainfo's)")
    args = ap.parse_args()
    mi = MediaInfo()
    tag = args.tag or mi.version()
    kinds = mi.kinds()
    files = {f"{k}.csv": f"Source/Resource/Text/Stream/{k}.csv" for k in kinds}
    files["LICENSE-MediaInfoLib"] = "LICENSE"
    got = {name: fetch(tag, path) for name, path in files.items()}  # all or nothing
    DEST.mkdir(parents=True, exist_ok=True)
    for old in DEST.glob("*.csv"):
        if old.name not in got:
            old.unlink()
    for name, data in got.items():
        (DEST / name).write_bytes(data)
    (DEST / "TAG").write_text(tag + "\n")
    print(f"{len(got)} files from MediaInfoLib {tag} ({', '.join(kinds)}) -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
