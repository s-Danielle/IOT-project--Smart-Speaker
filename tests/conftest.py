"""Shared test setup: put Main/ on the import path and swap the Pi-only libraries for fakes.

The fakes are installed before any test imports the speaker's code, so
`import core.controller` works on a computer without the Pi's hardware.
"""

import importlib
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Main"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fakes  # noqa: E402

fakes.install_hardware_stubs()

from storage import JsonStore  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_hardware_fakes():
    fakes.reset_hardware_stubs()
    yield


# ---------------------------------------------------------------------------
# A real server on this computer, for tests of the web routes
# ---------------------------------------------------------------------------
# It listens on 127.0.0.1 on a free port for the length of one test and keeps its data in a
# temporary folder. Nothing in the program's own folders, and no real network, is touched.

@pytest.fixture(scope="module")
def server_module(tmp_path_factory):
    """Import server.py without letting it create folders in the program's own directory."""
    from utils import shared_dirs

    made = []
    real_ensure, real_makedirs = shared_dirs.ensure_shared_dir, os.makedirs
    shared_dirs.ensure_shared_dir = lambda *a, **k: made.append(a)
    os.makedirs = lambda *a, **k: made.append(a)
    sys.modules.pop("server", None)
    try:
        module = importlib.import_module("server")
    finally:
        shared_dirs.ensure_shared_dir, os.makedirs = real_ensure, real_makedirs
    yield module
    sys.modules.pop("server", None)


@pytest.fixture
def api(server_module, tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    store = JsonStore(str(tmp_path / "server_data.json"), today=lambda: "2026-10-03")
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "DATA_FILE", store.path)
    monkeypatch.setattr(server_module, "UPLOADS_DIR", str(uploads))
    monkeypatch.setattr(server_module, "OLD_TAGS_FILE", str(tmp_path / "tags.json"))
    httpd = server_module.ThreadPoolHTTPServer(("127.0.0.1", 0), server_module.SpeakerHandler, max_workers=2)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    client = Client("http://127.0.0.1:%d" % httpd.server_address[1])
    client.store = store
    client.module = server_module
    client.tmp = tmp_path
    yield client
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


class Client:
    def call(self, method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read()
                return response.status, (json.loads(payload) if payload else None)
        except urllib.error.HTTPError as error:
            payload = error.read()
            try:
                return error.code, json.loads(payload)
            except ValueError:
                return error.code, None

    def __init__(self, base):
        self.base = base

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, body, **kw)

    def put(self, path, body=None, **kw):
        return self.call("PUT", path, body, **kw)

    def delete(self, path):
        return self.call("DELETE", path)


