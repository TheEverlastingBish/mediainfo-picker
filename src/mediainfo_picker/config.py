"""The user's choices, kept between runs in one small JSON file.

Stored in the platform's config location (on Linux `~/.config/mediainfo-picker/settings.json`).
Fields are saved as "Kind_Name" params, so a selection made on one file applies to any other; a
saved field the current file lacks is kept, not dropped, and used again when a file has it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths

FILE = "settings.json"


@dataclass
class Settings:
    mode: str = "default"
    selected: list[str] = field(default_factory=list)
    selected_initialised: bool = False  # becomes True the first time Selected fields is used
    last_dir: str = ""
    geometry: str = ""  # QMainWindow.saveGeometry(), hex
    splitter: str = ""  # QSplitter.saveState(), hex


def config_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    return Path(base) / FILE


def load() -> Settings:
    try:
        data = json.loads(config_path().read_text())
    except (OSError, ValueError):
        return Settings()
    known = Settings.__dataclass_fields__
    return Settings(**{k: v for k, v in data.items() if k in known})


def save(s: Settings) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), indent=2) + "\n")
    tmp.replace(p)
