import os
import shutil

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Tests that run the real mediainfo are skipped when it is not installed, which is right on a
    contributor's machine and wrong in CI, where a skip would hide that nothing was tested. CI sets
    REQUIRE_MEDIAINFO=1, and then a missing mediainfo stops the run instead."""
    if os.environ.get("REQUIRE_MEDIAINFO") and not shutil.which("mediainfo"):
        raise pytest.UsageError("REQUIRE_MEDIAINFO is set, but mediainfo is not on PATH")
