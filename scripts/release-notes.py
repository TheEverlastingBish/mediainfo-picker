#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md: the notes for its GitHub Release.

Example usage:

    uv run scripts/release-notes.py 0.2.0 > notes.md

Prints the lines under `## [0.2.0]`, up to the next `## ` heading or the link definitions at the
end (`[0.2.0]: https://…`), without the heading itself.
Exits 1 if the changelog has no section for that version, or an empty one, so a release cannot go
out without notes.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

CHANGELOG = pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def notes(text: str, version: str) -> str:
    heading = re.compile(rf"^## \[{re.escape(version)}\](\s|$)")
    link = re.compile(r"^\[[^\]]+\]: ")
    lines: list[str] | None = None
    for line in text.splitlines():
        if lines is None:
            if heading.match(line):
                lines = []
        elif line.startswith("## ") or link.match(line):
            break
        else:
            lines.append(line)
    if lines is None:
        raise LookupError(f"CHANGELOG.md has no section for {version}")
    body = "\n".join(lines).strip()
    if not body:
        raise LookupError(f"CHANGELOG.md's section for {version} is empty")
    return body + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the version, without the v: 0.2.0")
    args = parser.parse_args()
    try:
        sys.stdout.write(notes(CHANGELOG.read_text(encoding="utf-8"), args.version))
    except LookupError as exc:
        print(f"release-notes: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
