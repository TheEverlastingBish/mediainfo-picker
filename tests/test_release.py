"""The version is typed once, and the changelog has notes for it before it can be released."""

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

import mediainfo_picker

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "release-notes.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_version() -> str:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert isinstance(version, str)
    return version


def test_version_comes_from_pyproject() -> None:
    assert mediainfo_picker.__version__ == project_version()


def test_changelog_has_notes_for_this_version() -> None:
    result = subprocess.run([sys.executable, SCRIPT, project_version()], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stdout.startswith("## ")


CHANGELOG = """# Changelog

## [0.2.0] - 2026-11-16

### Added

- Two.

## [0.1.0] - 2026-11-15

- One.

[0.2.0]: https://example.com
"""


def test_notes_are_one_section() -> None:
    notes = load_script().notes
    assert notes(CHANGELOG, "0.2.0") == "### Added\n\n- Two.\n"
    assert notes(CHANGELOG, "0.1.0") == "- One.\n"  # not the links below it


def test_missing_or_empty_section_fails() -> None:
    notes = load_script().notes
    with pytest.raises(LookupError, match="no section"):
        notes(CHANGELOG, "0.3.0")
    with pytest.raises(LookupError, match="no section"):
        notes(CHANGELOG, "0.2")  # a prefix of 0.2.0 is not 0.2.0
    with pytest.raises(LookupError, match="empty"):
        notes("## [1.0.0]\n\n## [0.9.0]\n- x\n", "1.0.0")
