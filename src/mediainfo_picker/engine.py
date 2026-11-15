"""Everything that talks to mediainfo: reading a file's fields, and showing a chosen subset of them.

No Qt here, so it can be tested and reused without a display.

Three facts about mediainfo (MediaInfoLib v26.10) shape this module:

- A field's internal name comes from ``--Language=raw``, and that output lines up line for line
  with the normal one, before and after ``--HideParameter``/``--ShowParameter``. So the two can be
  zipped to learn which raw name each readable line belongs to.
- What mediainfo shows by default is read from the file itself: a field is shown by default when
  it appears in the plain ``--Language=raw`` output. The normal view mostly shows the ``/String``
  variant of a field (``Format/String``, not ``Format``), so that is the name to hide.
- ``--HideParameter`` accepts only names listed by ``--Info-Parameters``. Given any other, such as
  ``General_Attachments``, it reports it as unknown and prints nothing at all. Fields like that
  are removed from the text after the run instead.
"""

from __future__ import annotations

import enum
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("General", "Video", "Audio", "Text", "Other", "Image", "Menu")

_FIELD_LINE = re.compile(r"^(?P<key>\S.*?) *: (?P<value>.*)$")


class MediaInfoError(RuntimeError):
    """mediainfo is missing, failed, or printed something this module cannot read."""


class Mode(enum.Enum):
    DEFAULT = "default"
    FULL = "full"
    SELECTED = "selected"


@dataclass(frozen=True)
class Field:
    section: str  # as mediainfo heads it: "General", "Audio #2"
    name: str  # raw name: "UniqueID/String"
    label: str  # readable label: "Unique ID"
    value: str
    default: bool  # shown by plain `mediainfo`

    @property
    def kind(self) -> str:
        return kind_of(self.section)

    @property
    def param(self) -> str:
        """The name --HideParameter and --ShowParameter take: "General_UniqueID/String"."""
        return f"{self.kind}_{self.name}"


@dataclass
class Plan:
    """What to run for a mode and selection, and what to strip from its output afterwards."""

    args: list[str]
    remove: set[str] = field(default_factory=set)  # params to drop from the text after the run
    unshowable: list[str] = field(default_factory=list)  # ticked, hidden by default, not accepted


@dataclass
class Result:
    text: str
    command: str  # a shell command that prints exactly `text`
    removed_labels: list[str] = field(default_factory=list)


def kind_of(section: str) -> str:
    return section.split(" #", 1)[0]


class MediaInfo:
    """A mediainfo executable. ``path`` defaults to the one on PATH."""

    def __init__(self, path: str | None = None):
        found = path or shutil.which("mediainfo")
        if not found:
            raise MediaInfoError("mediainfo was not found on PATH. Install it, e.g. `pacman -S mediainfo`.")
        self.path = found

    def run(self, args: list[str]) -> str:
        """Run mediainfo; fail loudly. Measured on v26.10: an unknown --HideParameter name exits 1
        with its message on STDOUT, and a file that does not exist exits 0 with NO output."""
        try:
            proc = subprocess.run([self.path, *args], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MediaInfoError(f"could not run mediainfo: {exc}") from exc
        if proc.returncode != 0:
            raise MediaInfoError((proc.stdout + proc.stderr).strip() or f"mediainfo exited {proc.returncode}")
        if not proc.stdout.strip():
            raise MediaInfoError("mediainfo printed nothing: is the path a readable media file?")
        return proc.stdout

    def version(self) -> str:
        """"v26.10", from `mediainfo --Version`."""
        out = self.run(["--Version"])
        m = re.search(r"MediaInfoLib - (v[\w.]+)", out)
        return m.group(1) if m else out.strip().splitlines()[-1]

    def known_params(self) -> set[str]:
        """Every "Kind_Name" that --HideParameter/--ShowParameter accept."""
        return parse_info_parameters(self.run(["--Info-Parameters"]))

    def read_fields(self, path: str | Path) -> list[Field]:
        p = str(path)
        full = self.run(["--Full", p])
        raw = self.run(["--Full", "--Language=raw", p])
        default = self.run(["--Language=raw", p])
        return parse_fields(full, raw, default)

    def render(self, path: str | Path, plan: Plan) -> Result:
        p = str(path)
        text = self.run([*plan.args, p])
        removed: list[str] = []
        if plan.remove:
            raw = self.run([*plan.args, "--Language=raw", p])
            text, removed = strip_params(text, raw, plan.remove)
        return Result(text=text, command=command_line(self.display_name, plan.args, p, removed),
                      removed_labels=removed)

    @property
    def display_name(self) -> str:
        return "mediainfo" if shutil.which("mediainfo") == self.path else self.path


def parse_info_parameters(text: str) -> set[str]:
    params: set[str] = set()
    kind = None
    for line in text.splitlines():
        name = line.strip()
        if not name:
            continue
        if name in KINDS:
            kind = name
        elif kind:
            params.add(f"{kind}_{name}")
    return params


def _lines(text: str) -> list[str]:
    return text.splitlines()


def iter_sections(text: str):
    """Yield (section, line) for every line; section is None before the first heading."""
    section = None
    for line in _lines(text):
        if line and not _FIELD_LINE.match(line):
            section = line.strip()
        yield section, line


def parse_fields(full: str, full_raw: str, default_raw: str) -> list[Field]:
    readable, raw = _lines(full), _lines(full_raw)
    if len(readable) != len(raw):
        raise MediaInfoError(f"mediainfo's raw and readable outputs differ in length ({len(raw)} vs {len(readable)})")
    shown = {(sec, m.group("key")) for sec, line in iter_sections(default_raw) if (m := _FIELD_LINE.match(line))}
    fields: list[Field] = []
    for (sec, raw_line), text_line in zip(iter_sections(full_raw), readable):
        mr, mt = _FIELD_LINE.match(raw_line), _FIELD_LINE.match(text_line)
        if not (mr and mt and sec):
            continue
        name = mr.group("key")
        fields.append(Field(section=sec, name=name, label=mt.group("key"), value=mt.group("value"),
                            default=(sec, name) in shown))
    return fields


def plan(mode: Mode, fields: list[Field], selected: set[str], known: set[str]) -> Plan:
    """Turn a mode and a set of ticked params ("Kind_Name") into mediainfo arguments."""
    if mode is Mode.DEFAULT:
        return Plan(args=[])
    if mode is Mode.FULL:
        return Plan(args=["--Full"])
    default = {f.param for f in fields if f.default}
    present = {f.param for f in fields}
    hide = {p for p in default if p not in selected}
    show = {p for p in present - default if p in selected}
    p = Plan(args=[])
    if hide & known:
        p.args.append("--HideParameter=" + ",".join(sorted(hide & known)))
    if show & known:
        p.args.append("--ShowParameter=" + ",".join(sorted(show & known)))
    p.remove = hide - known
    p.unshowable = sorted(show - known)
    return p


def strip_params(text: str, raw: str, remove: set[str]) -> tuple[str, list[str]]:
    """Drop the lines of `text` whose raw name, in its section's kind, is in `remove`."""
    lines, raw_lines = _lines(text), _lines(raw)
    if len(lines) != len(raw_lines):
        raise MediaInfoError("mediainfo's raw and readable outputs differ in length; cannot remove fields")
    kept, removed = [], []
    for (sec, raw_line), line in zip(iter_sections(raw), lines):
        m = _FIELD_LINE.match(raw_line)
        if m and sec and f"{kind_of(sec)}_{m.group('key')}" in remove:
            label = _FIELD_LINE.match(line).group("key")
            removed.append((kind_of(sec), label))
            continue
        kept.append(line)
    out = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
    labels = sorted({f"{k}: {lab}" for k, lab in removed})
    return out, labels


def _ere(s: str) -> str:
    return re.sub(r"([.\[\]()*+?{}|^$\\/])", r"\\\1", s)


def command_line(prog: str, args: list[str], path: str, removed: list[str]) -> str:
    """The shell command that prints the same text: mediainfo, plus an awk filter for any fields
    removed after the run. `removed` holds "Kind: Label" items. The filter is per section, since a
    label such as "Encoded date" can appear in several sections and only one may be removed."""
    cmd = shlex.join([prog, *args, path])
    if not removed:
        return cmd
    conds = []
    for item in removed:
        kind, label = item.split(": ", 1)
        conds.append(f"(s ~ /^{kind}( #[0-9]+)?$/ && /^{_ere(label)} +: /)")
    awk = "!/ : /{s=$0} !(" + " || ".join(conds) + ")"
    return f"{cmd} | awk {shlex.quote(awk)}"
