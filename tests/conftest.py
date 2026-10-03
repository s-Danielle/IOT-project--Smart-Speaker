"""Shared test setup: put Main/ on the import path and swap the Pi-only libraries for fakes.

The fakes are installed before any test imports the speaker's code, so
`import core.controller` works on a computer without the Pi's hardware.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Main"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fakes  # noqa: E402

fakes.install_hardware_stubs()


@pytest.fixture(autouse=True)
def fresh_hardware_fakes():
    fakes.reset_hardware_stubs()
    yield
