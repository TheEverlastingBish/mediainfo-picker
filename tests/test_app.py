"""The window, driven without a display (Qt's offscreen platform), against the real mediainfo."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from mediainfo_picker import config
from mediainfo_picker.app import PARAM, Window
from mediainfo_picker.engine import MediaInfo, Mode

SAMPLE = str(Path(__file__).parent / "fixtures" / "sample.mkv")

pytestmark = pytest.mark.skipif(not shutil.which("mediainfo"), reason="mediainfo not installed")


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: path)
    return path


@pytest.fixture
def window(qapp: QApplication, settings_file: Path) -> Iterator[Window]:
    w = Window(MediaInfo())
    w.open_file(SAMPLE)
    yield w
    close(w)


def close(w: Window) -> None:
    """Close and delete the window now. processEvents() alone does not run deferred deletes, and a
    window left for interpreter shutdown crashed Python 3.11 at exit (none_dealloc, PySide6 6.12)."""
    w.close()
    w.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def checkable(w: Window) -> bool:
    return bool(next(w.items()).flags() & Qt.ItemFlag.ItemIsUserCheckable)


def untick(w: Window, params: set[str]) -> None:
    for item in w.items():
        if item.data(0, PARAM) in params:
            item.setCheckState(0, Qt.CheckState.Unchecked)


def test_default_shows_mediainfo_defaults_read_only(window: Window) -> None:
    assert window.mode is Mode.DEFAULT
    assert window.tree.isEnabled() and not checkable(window)
    assert "Sample Title" in window.output.toPlainText()
    assert window.command.text().startswith("mediainfo ")


def test_full_greys_the_list_out(window: Window) -> None:
    window.radios[Mode.FULL].setChecked(True)
    window.apply()
    assert not window.tree.isEnabled()
    assert "--Full" in window.command.text()


def test_selected_fields_starts_from_defaults_and_applies_ticks(window: Window) -> None:
    window.radios[Mode.SELECTED].setChecked(True)
    assert checkable(window)
    default_count = window.count.text()
    untick(window, {"General_Title", "General_Attachments"})
    assert window.count.text() != default_count
    window.apply()
    text = window.output.toPlainText()
    assert "Sample Title" not in text and "Attachments" not in text
    assert "--HideParameter=General_Title" in window.command.text()
    assert "Attachments" in window.statusBar().currentMessage()


def test_search_filters_the_list(window: Window) -> None:
    window.search.setText("unique id")
    visible = [i.text(0) for i in window.items() if not i.isHidden()]
    assert visible and all("unique id" in t.lower() for t in visible)


def test_selection_is_saved_and_restored(qapp: QApplication, settings_file: Path) -> None:
    w = Window(MediaInfo())
    w.open_file(SAMPLE)
    w.radios[Mode.SELECTED].setChecked(True)
    untick(w, {"General_Title"})
    close(w)
    assert settings_file.is_file()

    again = Window(MediaInfo())
    again.open_file(SAMPLE)
    assert again.mode is Mode.SELECTED
    assert "General_Title" not in again.selected
    assert "Sample Title" not in again.output.toPlainText()
    close(again)


def test_clear_all_and_defaults_only_in_selected_fields(window: Window) -> None:
    assert not window.clear_btn.isEnabled() and not window.defaults_btn.isEnabled()
    window.radios[Mode.SELECTED].setChecked(True)
    assert window.clear_btn.isEnabled() and window.defaults_btn.isEnabled()
    defaults = window.count.text()

    window.selected.add("Other_Kind_Field")  # a saved field this file lacks
    window.clear_selection()
    assert window.count.text().startswith("0 of ")
    assert all(i.checkState(0) == Qt.CheckState.Unchecked for i in window.items())
    assert "Other_Kind_Field" in window.selected

    window.select_defaults()
    assert window.count.text() == defaults
    assert "Other_Kind_Field" in window.selected


def test_expand_collapse_and_search_restores_what_was_open(window: Window) -> None:
    assert not window.expanded_sections()
    window.set_expanded(True)
    assert window.expanded_sections() == {t.text(0) for t in window.sections()}
    window.set_expanded(False)
    assert not window.expanded_sections()

    general = next(window.sections())
    general.setExpanded(True)
    window.search.setText("unique id")
    assert window.expanded_sections()
    window.search.setText("")
    assert window.expanded_sections() == {general.text(0)}


def test_reopening_keeps_open_sections(window: Window) -> None:
    general = next(window.sections())
    general.setExpanded(True)
    name = general.text(0)  # the item itself is deleted when the tree is rebuilt
    window.open_file(SAMPLE)
    assert window.expanded_sections() == {name}


def test_left_panel_cannot_squeeze_the_count(window: Window) -> None:
    assert not window.splitter.childrenCollapsible()
    window.splitter.setSizes([0, 2000])
    left = window.splitter.widget(0)
    assert left is not None and left.width() >= left.minimumSizeHint().width()
