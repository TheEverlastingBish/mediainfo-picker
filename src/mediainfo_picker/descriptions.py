"""Field descriptions for tooltips, from MediaInfoLib's own field tables.

The tables are bundled in data/mediainfo-csv/, one `<Kind>.csv` per stream kind (BSD-2-Clause,
MediaArea.net SARL; see LICENSE-MediaInfoLib and TAG there, and scripts/update-mediainfo-csv.py to
refresh them). They are semicolon-separated, one field per line: the name first and the
description in the seventh column. Only descriptions are read from them: what a field is called
and whether mediainfo shows it by default come from the installed mediainfo, which the tables can
lag behind. A field missing from them (such as General's `Attachments`) simply has no description.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable


def _data() -> Traversable:
    return resources.files("mediainfo_picker") / "data" / "mediainfo-csv"


@cache
def descriptions() -> dict[str, str]:
    """{"General_UniqueID/String": "The unique ID for this stream, ..."}"""
    out: dict[str, str] = {}
    for f in _data().iterdir():
        if not f.name.endswith(".csv"):
            continue
        kind = f.name.removesuffix(".csv")
        for line in f.read_text(encoding="utf-8").splitlines():
            cols = line.split(";")
            if len(cols) >= 7 and cols[0] and cols[6].strip():
                out[f"{kind}_{cols[0]}"] = cols[6].strip()
    return out


def bundled_kinds() -> set[str]:
    return {f.name.removesuffix(".csv") for f in _data().iterdir() if f.name.endswith(".csv")}


def describe(param: str) -> str:
    return descriptions().get(param, "")


def data_tag() -> str:
    f = _data() / "TAG"
    return f.read_text().strip() if f.is_file() else ""
