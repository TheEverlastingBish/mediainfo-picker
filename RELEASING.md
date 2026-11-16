# Releasing

A release is a version number, a signed tag `vX.Y.Z` on `main`, the packages on PyPI and a GitHub
Release with notes. Pushing the tag does everything after the tag: `.github/workflows/release.yml`
runs CI, builds the wheel and sdist, publishes them to PyPI and creates the GitHub Release with the
notes from `CHANGELOG.md`. No token is stored anywhere: PyPI trusts that workflow directly
([Trusted Publishing](https://docs.pypi.org/trusted-publishers/)).

Versions follow [Semantic Versioning](https://semver.org/). While it is 0.x, a new feature bumps
the middle number (0.2.0 → 0.3.0) and a fix bumps the last (0.2.0 → 0.2.1).

## Steps

1. **A release pull request**, `release/X.Y.Z`, that only:
   - sets `version` in `pyproject.toml` (the one place it is typed; the app reads it from the
     installed package);
   - runs `uv lock`, which records the new version in `uv.lock`;
   - adds `## [X.Y.Z] - YYYY-MM-DD` to `CHANGELOG.md`, with the link at the bottom.

   The tests fail if the changelog has no section for the version in `pyproject.toml`.
2. **Check the app by hand on the operating systems CI cannot look at**: start it on Windows and
   macOS, open a file, switch the modes, apply, copy the output and the command. CI runs the tests
   on all three, but never sees the window.
3. **Merge** (squash), then update a local `main`.
4. **Optional dry run on TestPyPI**: Actions → Release → *Run workflow* on `main`. It runs CI,
   builds, and publishes to [TestPyPI](https://test.pypi.org/project/mediainfo-picker/) only. Then
   try it:

   ```bash
   uv tool install --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match \
     mediainfo-picker==X.Y.Z
   ```

   (TestPyPI accepts each version once, like PyPI; a second dry run of the same version fails at
   the upload.)
5. **Tag and push the tag**:

   ```bash
   git tag -s vX.Y.Z -m "mediainfo-picker X.Y.Z: <one line>"
   git push origin vX.Y.Z
   ```

   The workflow refuses a tag that does not match `pyproject.toml`, or a version with no
   changelog notes.
6. **Check**: the Release has its notes and two packages,
   [PyPI](https://pypi.org/project/mediainfo-picker/) shows the version, and
   `uv tool install mediainfo-picker==X.Y.Z` installs it, with that version in the status bar.

A version with `a`, `b` or `rc` and a number at the end (`0.3.0rc1`) is marked as a pre-release
on GitHub; PyPI installs it only when asked for by number.

## If a release goes wrong

PyPI never accepts the same version twice, even after a deletion. If the upload fails, fix the
cause and re-run the failed jobs. If a broken version is out, *yank* it on PyPI (installs skip it
unless it is asked for by number) and release a fix with the next patch number. Don't move a tag
that has been pushed.

## One-time setup (done)

- PyPI and TestPyPI: a trusted publisher for owner `TheEverlastingBish`, repository
  `mediainfo-picker`, workflow `release.yml`, environment `pypi` (TestPyPI: `testpypi`).
- GitHub: the environments `pypi` and `testpypi` (created by the first run that uses them).
