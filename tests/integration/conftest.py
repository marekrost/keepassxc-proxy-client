"""Integration-test fixtures.

The suite is designed to run inside the `client` service of
`tests/integration/docker/docker-compose.yml`. The `keepassxc` sibling
service must be reachable through the `kpxc-socket` named volume mounted
at $XDG_RUNTIME_DIR. See tests/integration/README.md for the full setup.

A few tests need a human to click "Allow" in KeePassXC's Browser
Integration dialogs. Those tests use the `human_step` fixture, which
prints a clear instruction pointing at the noVNC URL and waits for the
human (or for an auto-confirm timeout, if KPXC_TEST_AUTOCONFIRM=1).
"""
from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

import pytest


SOCKET_NAME = "org.keepassxc.KeePassXC.BrowserServer"


def _socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
    return os.path.join(runtime, SOCKET_NAME)


def _socket_ready(path: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(path)
                s.close()
                return True
            except OSError:
                pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session", autouse=True)
def _require_keepassxc_socket():
    """Skip the whole suite if the KeePassXC socket isn't reachable."""
    path = _socket_path()
    if not _socket_ready(path):
        pytest.skip(
            f"KeePassXC Browser Integration socket not reachable at {path}. "
            "See tests/integration/README.md for setup."
        )


@pytest.fixture
def socket_path() -> str:
    return _socket_path()


@pytest.fixture
def keystore_file(tmp_path) -> Path:
    """Per-test empty keystore — keeps tests isolated from each other."""
    return tmp_path / "keystore.json"


@pytest.fixture
def human_step():
    """Return a callable that pauses the test for a human action via noVNC.

    Usage:
        def test_x(human_step):
            human_step("click Allow in the association dialog")

    Behavior:
      - Interactive (default): prints the instruction and waits on stdin.
      - Auto-confirm (KPXC_TEST_AUTOCONFIRM=1): waits `KPXC_TEST_HUMAN_WAIT`
        seconds (default 10) for an external watcher (e.g. an xdotool
        script inside the keepassxc container) to perform the click.
    """
    novnc = os.environ.get("KPXC_TEST_NOVNC_URL", "http://localhost:6080")
    autoconfirm = os.environ.get("KPXC_TEST_AUTOCONFIRM") == "1"
    wait_seconds = float(os.environ.get("KPXC_TEST_HUMAN_WAIT", "10"))

    def _prompt(action: str) -> None:
        banner = (
            "\n"
            "============================================================\n"
            f" HUMAN ACTION REQUIRED — open {novnc}\n"
            f"   → {action}\n"
            "============================================================\n"
        )
        print(banner, file=sys.stderr, flush=True)
        if autoconfirm:
            time.sleep(wait_seconds)
            return
        try:
            input("press ENTER once done... ")
        except EOFError:
            time.sleep(wait_seconds)

    return _prompt
