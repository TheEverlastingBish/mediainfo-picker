"""The window: pick a file, choose Default / Full / Selected fields, apply, copy."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__, config
from .descriptions import data_tag, describe
from .engine import Field, MediaInfo, MediaInfoError, Mode, plan

PARAM = Qt.ItemDataRole.UserRole


class Window(QMainWindow):
    def __init__(self, mi: MediaInfo | None, error: str = ""):
        super().__init__()
        self.mi = mi
        self.settings = config.load()
        self.fields: list[Field] = []
        self.known: set[str] = mi.known_params() if mi else set()
        self.path = ""
        self.selected: set[str] = set(self.settings.selected)
        self._updating = False
        self.setWindowTitle("mediainfo-picker")
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        # File row
        self.file_edit = QLineEdit(readOnly=True, placeholderText="Choose a media file…")
        browse = QPushButton("Browse…", clicked=self.browse)
        top = QHBoxLayout()
        top.addWidget(QLabel("File:"))
        top.addWidget(self.file_edit, 1)
        top.addWidget(browse)

        # Left: mode, search, palette
        self.mode_group = QButtonGroup(self)
        self.radios = {}
        modes = QHBoxLayout()
        for mode, text in ((Mode.DEFAULT, "Default"), (Mode.FULL, "Full"), (Mode.SELECTED, "Selected fields")):
            rb = QRadioButton(text)
            self.mode_group.addButton(rb)
            self.radios[mode] = rb
            modes.addWidget(rb)
        modes.addStretch(1)
        self.search = QLineEdit(placeholderText="Search fields…", clearButtonEnabled=True,
                                textChanged=self.apply_filter)
        self.count = QLabel()
        srow = QHBoxLayout()
        srow.addWidget(self.search, 1)
        srow.addWidget(self.count)
        self.tree = QTreeWidget(headerHidden=True, itemChanged=self.item_changed)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addLayout(modes)
        lv.addLayout(srow)
        lv.addWidget(self.tree, 1)

        # Right: output
        self.output = QPlainTextEdit(readOnly=True, lineWrapMode=QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setFont(mono)
        self.splitter = QSplitter()
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.output)
        self.splitter.setStretchFactor(1, 2)

        # Bottom: command and buttons
        self.command = QLineEdit(readOnly=True, placeholderText="The equivalent mediainfo command appears here")
        self.command.setFont(mono)
        self.apply_btn = QPushButton("Apply", clicked=self.apply, default=True)
        copy_out = QPushButton("Copy output", clicked=lambda: self.copy(self.output.toPlainText(), "Output"))
        copy_cmd = QPushButton("Copy command", clicked=lambda: self.copy(self.command.text(), "Command"))
        brow = QHBoxLayout()
        brow.addStretch(1)
        for b in (self.apply_btn, copy_out, copy_cmd):
            brow.addWidget(b)

        central = QWidget()
        v = QVBoxLayout(central)
        v.addLayout(top)
        v.addWidget(self.splitter, 1)
        v.addWidget(self.command)
        v.addLayout(brow)
        self.setCentralWidget(central)

        # Status bar: the mediainfo in use, always
        self.version_label = QLabel()
        self.statusBar().addPermanentWidget(self.version_label)
        if mi:
            tag = data_tag()
            self.version_label.setText(f"MediaInfo {mi.version()} · descriptions {tag} · mediainfo-picker {__version__}")
        else:
            self.version_label.setText("MediaInfo not found")
            self.statusBar().showMessage(error)
            self.apply_btn.setEnabled(False)
            browse.setEnabled(False)

        self.radios[Mode(self.settings.mode)].setChecked(True)
        self.mode_group.buttonToggled.connect(self.mode_changed)
        if self.settings.geometry:
            self.restoreGeometry(QByteArray.fromHex(self.settings.geometry.encode()))
        else:
            self.resize(1200, 760)
        if self.settings.splitter:
            self.splitter.restoreState(QByteArray.fromHex(self.settings.splitter.encode()))
        self.update_palette_state()

    # --- mode and palette ---------------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return next(m for m, rb in self.radios.items() if rb.isChecked())

    def mode_changed(self, button, checked):
        if not checked:
            return
        if self.mode is Mode.SELECTED and not self.settings.selected_initialised and self.fields:
            self.selected = {f.param for f in self.fields if f.default}
            self.settings.selected_initialised = True
        self.refresh_ticks()
        self.update_palette_state()

    def update_palette_state(self):
        """Default: ticks shown, read-only. Full: greyed out. Selected fields: editable."""
        self.tree.setEnabled(self.mode is not Mode.FULL)
        editable = self.mode is Mode.SELECTED
        self._updating = True
        for item in self.items():
            flags = item.flags()
            flags = flags | Qt.ItemFlag.ItemIsUserCheckable if editable else flags & ~Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            f = top.flags() | Qt.ItemFlag.ItemIsAutoTristate
            top.setFlags(f | Qt.ItemFlag.ItemIsUserCheckable if editable else f & ~Qt.ItemFlag.ItemIsUserCheckable)
        self._updating = False
        self.update_count()

    def items(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                yield top.child(j)

    def ticked(self, param: str, default: bool) -> bool:
        if self.mode is Mode.SELECTED:
            return param in self.selected
        if self.mode is Mode.FULL:
            return True
        return default

    def build_tree(self):
        self._updating = True
        self.tree.clear()
        tops: dict[str, QTreeWidgetItem] = {}
        for f in self.fields:
            top = tops.get(f.section)
            if top is None:
                top = tops[f.section] = QTreeWidgetItem(self.tree, [f.section])
                top.setFlags(top.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
            label = f.label if f.label == f.name else f"{f.label}  ({f.name})"
            item = QTreeWidgetItem(top, [label])
            item.setData(0, PARAM, f.param)
            item.setData(0, PARAM + 1, f.default)
            tip = describe(f.param)
            item.setToolTip(0, f"{f.param}\n{f.value}" + (f"\n\n{tip}" if tip else ""))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if self.ticked(f.param, f.default) else Qt.CheckState.Unchecked)
        self._updating = False
        self.apply_filter(self.search.text())

    def refresh_ticks(self):
        self._updating = True
        for item in self.items():
            on = self.ticked(item.data(0, PARAM), item.data(0, PARAM + 1))
            item.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self._updating = False
        self.update_count()

    def item_changed(self, item: QTreeWidgetItem, _col: int):
        if self._updating or self.mode is not Mode.SELECTED:
            return
        if item.parent() is None:  # a section's tristate box; its children change and report themselves
            return
        param = item.data(0, PARAM)
        on = item.checkState(0) == Qt.CheckState.Checked
        (self.selected.add if on else self.selected.discard)(param)
        # The same param in another section of that kind (Audio #1 and #2) follows: mediainfo hides
        # and shows by kind, not by stream.
        self._updating = True
        for other in self.items():
            if other is not item and other.data(0, PARAM) == param:
                other.setCheckState(0, item.checkState(0))
        self._updating = False
        self.update_count()

    def apply_filter(self, text: str):
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            visible = 0
            for j in range(top.childCount()):
                child = top.child(j)
                hit = not needle or needle in child.text(0).lower()
                child.setHidden(not hit)
                visible += hit
            top.setHidden(visible == 0)
            top.setExpanded(bool(needle) and visible > 0)
        self.update_count()

    def update_count(self):
        params = {f.param for f in self.fields}
        if self.mode is Mode.FULL:
            n = len(params)
        elif self.mode is Mode.DEFAULT:
            n = len({f.param for f in self.fields if f.default})
        else:
            n = len(self.selected & params)
        self.count.setText(f"{n} of {len(params)} fields")

    # --- file, apply, copy ----------------------------------------------------------------------

    def browse(self):
        start = self.settings.last_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose a media file", start)
        if path:
            self.open_file(path)

    def open_file(self, path: str):
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.fields = self.mi.read_fields(path)
        except MediaInfoError as exc:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "mediainfo", str(exc))
            return
        QGuiApplication.restoreOverrideCursor()
        self.path = path
        self.file_edit.setText(path)
        self.settings.last_dir = str(Path(path).parent)
        if self.mode is Mode.SELECTED and not self.settings.selected_initialised:
            self.selected = {f.param for f in self.fields if f.default}
            self.settings.selected_initialised = True
        self.build_tree()
        self.update_palette_state()
        self.apply()

    def apply(self):
        if not self.path:
            self.statusBar().showMessage("Choose a file first.", 4000)
            return
        p = plan(self.mode, self.fields, self.selected, self.known)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.mi.render(self.path, p)
        except MediaInfoError as exc:
            QGuiApplication.restoreOverrideCursor()
            self.output.setPlainText(f"mediainfo failed:\n\n{exc}")
            return
        QGuiApplication.restoreOverrideCursor()
        self.output.setPlainText(result.text)
        self.command.setText(result.command)
        self.command.setCursorPosition(0)
        notes = []
        if result.removed_labels:
            notes.append("removed from the text (mediainfo cannot hide them): " + ", ".join(result.removed_labels))
        if p.unshowable:
            notes.append("cannot be shown outside Full: " + ", ".join(p.unshowable))
        self.statusBar().showMessage(" · ".join(notes), 0 if notes else 1)

    def copy(self, text: str, what: str):
        if text:
            QGuiApplication.clipboard().setText(text)
            self.statusBar().showMessage(f"{what} copied to the clipboard.", 3000)

    def closeEvent(self, event):
        s = self.settings
        s.mode = self.mode.value
        s.selected = sorted(self.selected)
        s.geometry = bytes(self.saveGeometry().toHex()).decode()
        s.splitter = bytes(self.splitter.saveState().toHex()).decode()
        try:
            config.save(s)
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("mediainfo-picker")
    try:
        mi, err = MediaInfo(), ""
    except MediaInfoError as exc:
        mi, err = None, str(exc)
    w = Window(mi, err)
    w.show()
    if mi and len(sys.argv) > 1:
        w.open_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
