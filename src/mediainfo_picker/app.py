"""The window: pick a file, choose Default / Full / Selected fields, apply, copy."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
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

APP_NAME = "MediaInfo Picker"
ACCENT = "#17707F"  # the banner and the icon (data/icon.svg) share this colour
PARAM = Qt.ItemDataRole.UserRole  # an item's "Kind_Name"
DEFAULT = Qt.ItemDataRole.UserRole + 1  # whether mediainfo shows it by default
CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable


def _check(on: bool) -> Qt.CheckState:
    return Qt.CheckState.Checked if on else Qt.CheckState.Unchecked


def app_icon() -> QIcon:
    return QIcon(str(files("mediainfo_picker") / "data" / "icon.svg"))


def banner() -> QWidget:
    """The strip across the top: the icon and the app's name on the accent colour."""
    strip = QWidget()
    strip.setObjectName("banner")
    strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    strip.setStyleSheet(f"#banner {{ background: {ACCENT}; }} #banner QLabel {{ color: white; }}")
    icon = QLabel()
    icon.setPixmap(app_icon().pixmap(22, 22))
    title = QLabel(APP_NAME)
    font = QFont(title.font())
    font.setPointSizeF(font.pointSizeF() * 1.3)
    font.setBold(True)
    title.setFont(font)
    row = QHBoxLayout(strip)
    row.setContentsMargins(10, 6, 10, 6)
    row.addWidget(icon)
    row.addWidget(title)
    row.addStretch(1)
    return strip


class Window(QMainWindow):
    def __init__(self, mi: MediaInfo | None, error: str = "") -> None:
        super().__init__()
        self.mi = mi
        self.settings = config.load()
        self.fields: list[Field] = []
        self.known: set[str] = mi.known_params() if mi else set()
        self.path = ""
        self.selected: set[str] = set(self.settings.selected)
        self._updating = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        # File row
        self.file_edit = QLineEdit(readOnly=True, placeholderText="Choose a media file…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        top = QHBoxLayout()
        top.addWidget(QLabel("File:"))
        top.addWidget(self.file_edit, 1)
        top.addWidget(browse)

        # Left: mode, search, palette
        self.mode_group = QButtonGroup(self)
        self.radios: dict[Mode, QRadioButton] = {}
        modes = QHBoxLayout()
        for mode, text in ((Mode.DEFAULT, "Default"), (Mode.FULL, "Full"), (Mode.SELECTED, "Selected fields")):
            rb = QRadioButton(text)
            self.mode_group.addButton(rb)
            self.radios[mode] = rb
            modes.addWidget(rb)
        modes.addStretch(1)
        self.search = QLineEdit(placeholderText="Search fields…", clearButtonEnabled=True)
        self.search.textChanged.connect(self.apply_filter)
        self._expanded_before_search: set[str] | None = None
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(self.item_changed)
        expand = QPushButton("Expand all")
        expand.clicked.connect(lambda: self.set_expanded(True))
        collapse = QPushButton("Collapse all")
        collapse.clicked.connect(lambda: self.set_expanded(False))
        self.defaults_btn = QPushButton("Defaults")
        self.defaults_btn.setToolTip("Tick exactly the fields mediainfo shows by default")
        self.defaults_btn.clicked.connect(self.select_defaults)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.setToolTip("Untick every field")
        self.clear_btn.clicked.connect(self.clear_selection)
        tools = QHBoxLayout()
        for b in (expand, collapse):
            tools.addWidget(b)
        tools.addStretch(1)
        for b in (self.defaults_btn, self.clear_btn):
            tools.addWidget(b)
        self.count = QLabel()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addLayout(modes)
        lv.addWidget(self.search)
        lv.addLayout(tools)
        lv.addWidget(self.tree, 1)
        lv.addWidget(self.count)

        # Right: output
        self.output = QPlainTextEdit(readOnly=True, lineWrapMode=QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setFont(mono)
        self.splitter = QSplitter()
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.output)
        self.splitter.setChildrenCollapsible(False)  # the left panel never shrinks below its buttons
        self.splitter.setStretchFactor(1, 2)

        # Bottom: command and buttons
        self.command = QLineEdit(readOnly=True, placeholderText="The equivalent mediainfo command appears here")
        self.command.setFont(mono)
        self.command.setToolTip(
            "The mediainfo command that prints the output above, for a Unix-style shell "
            "(bash, zsh; on Windows, Git Bash or WSL)"
        )
        self.apply_btn = QPushButton("Apply", default=True)
        self.apply_btn.clicked.connect(self.apply)
        copy_out = QPushButton("Copy output")
        copy_out.clicked.connect(lambda: self.copy(self.output.toPlainText(), "Output"))
        copy_cmd = QPushButton("Copy command")
        copy_cmd.setToolTip(self.command.toolTip())
        copy_cmd.clicked.connect(lambda: self.copy(self.command.text(), "Command"))
        brow = QHBoxLayout()
        brow.addStretch(1)
        for b in (self.apply_btn, copy_out, copy_cmd):
            brow.addWidget(b)

        # Log: what happened and anything worth knowing about the last run. The status bar is kept
        # for the versions and for errors.
        self.log_view = QPlainTextEdit(readOnly=True, maximumBlockCount=500)
        self.log_view.setPlaceholderText("Messages appear here")
        lines = self.log_view.fontMetrics().lineSpacing()
        self.log_view.setFixedHeight(lines * 5 + 12)

        central = QWidget()
        v = QVBoxLayout(central)
        v.addLayout(top)
        v.addWidget(self.splitter, 1)
        v.addWidget(self.command)
        v.addLayout(brow)
        v.addWidget(self.log_view)
        outer = QWidget()
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(0)
        ov.addWidget(banner())
        ov.addWidget(central, 1)
        self.setCentralWidget(outer)

        # Status bar: the versions in use, always, and errors
        self.version_label = QLabel()
        self.statusBar().addPermanentWidget(self.version_label)
        if mi:
            text = f"MediaInfo {mi.version()} · Descriptions {data_tag()} · {APP_NAME} v{__version__}"
            self.version_label.setText(text)
        else:
            self.version_label.setText(f"MediaInfo not found · {APP_NAME} v{__version__}")
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
        else:
            self.splitter.setSizes([480, max(self.width() - 480, 400)])
        self.update_palette_state()

    # --- the tree -------------------------------------------------------------------------------

    def sections(self) -> Iterator[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item is None:
                raise RuntimeError(f"tree has no top-level item {i}")
            yield item

    def items(self) -> Iterator[QTreeWidgetItem]:
        for top in self.sections():
            for j in range(top.childCount()):
                child = top.child(j)
                if child is None:
                    raise RuntimeError(f"section {top.text(0)!r} has no child {j}")
                yield child

    # --- mode and palette -----------------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return next(m for m, rb in self.radios.items() if rb.isChecked())

    def mode_changed(self, _button: QAbstractButton, checked: bool) -> None:
        if not checked:
            return
        if self.mode is Mode.SELECTED and not self.settings.selected_initialised and self.fields:
            self.selected = {f.param for f in self.fields if f.default}
            self.settings.selected_initialised = True
        self.refresh_ticks()
        self.update_palette_state()

    def update_palette_state(self) -> None:
        """Default: ticks shown, read-only. Full: greyed out. Selected fields: editable."""
        self.tree.setEnabled(self.mode is not Mode.FULL)
        editable = self.mode is Mode.SELECTED
        self.defaults_btn.setEnabled(editable)
        self.clear_btn.setEnabled(editable)
        self._updating = True
        for item in [*self.items(), *self.sections()]:
            flags = item.flags()
            item.setFlags(flags | CHECKABLE if editable else flags & ~CHECKABLE)
        self._updating = False
        self.update_count()

    def ticked(self, param: str, default: bool) -> bool:
        if self.mode is Mode.SELECTED:
            return param in self.selected
        return self.mode is Mode.FULL or default

    def build_tree(self) -> None:
        # A new file keeps the sections you had open (before any search opened the rest).
        expanded = self._expanded_before_search
        if expanded is None:
            expanded = self.expanded_sections()
        self._updating = True
        self.tree.clear()
        tops: dict[str, QTreeWidgetItem] = {}
        for f in self.fields:
            top = tops.get(f.section)
            if top is None:
                top = tops[f.section] = QTreeWidgetItem(self.tree, [f.section])
                top.setFlags(top.flags() | Qt.ItemFlag.ItemIsAutoTristate | CHECKABLE)
            label = f.label if f.label == f.name else f"{f.label}  ({f.name})"
            item = QTreeWidgetItem(top, [label])
            item.setData(0, PARAM, f.param)
            item.setData(0, DEFAULT, f.default)
            tip = describe(f.param)
            item.setToolTip(0, f"{f.param}\n{f.value}" + (f"\n\n{tip}" if tip else ""))
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, _check(self.ticked(f.param, f.default)))
        for top in self.sections():
            top.setExpanded(top.text(0) in expanded)
        self._updating = False
        self._expanded_before_search = None
        self.apply_filter(self.search.text())

    def expanded_sections(self) -> set[str]:
        return {top.text(0) for top in self.sections() if top.isExpanded()}

    def set_expanded(self, on: bool) -> None:
        for top in self.sections():
            if not top.isHidden():
                top.setExpanded(on)

    def set_selection(self, params: set[str]) -> None:
        """Replace the ticks for this file's fields; saved fields this file lacks are kept."""
        here = {f.param for f in self.fields}
        self.selected = (self.selected - here) | (params & here)
        self.refresh_ticks()

    def select_defaults(self) -> None:
        self.set_selection({f.param for f in self.fields if f.default})

    def clear_selection(self) -> None:
        self.set_selection(set())

    def refresh_ticks(self) -> None:
        self._updating = True
        for item in self.items():
            item.setCheckState(0, _check(self.ticked(item.data(0, PARAM), item.data(0, DEFAULT))))
        self._updating = False
        self.update_count()

    def item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._updating or self.mode is not Mode.SELECTED:
            return
        if item.parent() is None:  # a section's tristate box; its children change and report themselves
            return
        param = item.data(0, PARAM)
        if item.checkState(0) == Qt.CheckState.Checked:
            self.selected.add(param)
        else:
            self.selected.discard(param)
        # The same param in another section of that kind (Audio #1 and #2) follows: mediainfo hides
        # and shows by kind, not by stream.
        self._updating = True
        for other in self.items():
            if other is not item and other.data(0, PARAM) == param:
                other.setCheckState(0, item.checkState(0))
        self._updating = False
        self.update_count()

    def apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        # Searching opens every section with a hit; clearing the search puts back what was open.
        restore = None
        if needle and self._expanded_before_search is None:
            self._expanded_before_search = self.expanded_sections()
        elif not needle and self._expanded_before_search is not None:
            restore, self._expanded_before_search = self._expanded_before_search, None
        for top in self.sections():
            visible = 0
            for j in range(top.childCount()):
                child = top.child(j)
                if child is None:
                    continue
                hit = not needle or needle in child.text(0).lower()
                child.setHidden(not hit)
                visible += hit
            top.setHidden(visible == 0)
            if needle:
                top.setExpanded(visible > 0)
            elif restore is not None:
                top.setExpanded(top.text(0) in restore)
        self.update_count()

    def update_count(self) -> None:
        params = {f.param for f in self.fields}
        if self.mode is Mode.FULL:
            n = len(params)
        elif self.mode is Mode.DEFAULT:
            n = len({f.param for f in self.fields if f.default})
        else:
            n = len(self.selected & params)
        self.count.setText(f"{n} of {len(params)} fields")

    # --- file, apply, copy ----------------------------------------------------------------------

    def browse(self) -> None:
        start = self.settings.last_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose a media file", start)
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        if self.mi is None:
            return
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.fields = self.mi.read_fields(path)
        except MediaInfoError as exc:
            QMessageBox.warning(self, "mediainfo", str(exc))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.path = path
        self.file_edit.setText(path)
        self.log(f"Opened {path}")
        self.settings.last_dir = str(Path(path).parent)
        if self.mode is Mode.SELECTED and not self.settings.selected_initialised:
            self.selected = {f.param for f in self.fields if f.default}
            self.settings.selected_initialised = True
        self.build_tree()
        self.update_palette_state()
        self.apply()

    def apply(self) -> None:
        if self.mi is None:
            return
        if not self.path:
            self.log("Choose a file first.")
            return
        p = plan(self.mode, self.fields, self.selected, self.known)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.mi.render(self.path, p)
        except MediaInfoError as exc:
            self.output.setPlainText(f"mediainfo failed:\n\n{exc}")
            self.statusBar().showMessage(f"mediainfo failed: {exc}")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.statusBar().clearMessage()
        self.output.setPlainText(result.text)
        self.command.setText(result.command)
        self.command.setCursorPosition(0)
        self.log(f"Applied {self.radios[self.mode].text()}: {self.count.text()}.")
        if result.removed_labels:
            self.log("Removed from the text (mediainfo cannot hide them): " + ", ".join(result.removed_labels))
        if p.unshowable:
            self.log("Cannot be shown outside Full: " + ", ".join(p.unshowable))

    def log(self, message: str) -> None:
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def copy(self, text: str, what: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if text and clipboard is not None:
            clipboard.setText(text)
            self.log(f"{what} copied to the clipboard.")

    def closeEvent(self, event: QCloseEvent) -> None:
        s = self.settings
        s.mode = self.mode.value
        s.selected = sorted(self.selected)
        s.geometry = bytes(self.saveGeometry().toHex().data()).decode()
        s.splitter = bytes(self.splitter.saveState().toHex().data()).decode()
        try:
            config.save(s)
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("mediainfo-picker")  # also names the settings folder: keep it
    app.setWindowIcon(app_icon())
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
