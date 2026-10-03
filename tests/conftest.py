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


@pytest.fixture(params=["json", "sqlite"])
def api(request, server_module, tmp_path, monkeypatch):
    """A running server with its data in a temporary folder, once with each kind of data store."""
    kind = request.param
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("SPEAKER_STORAGE", kind)  # what a restart (start_storage) will pick
    monkeypatch.setenv("SPEAKER_STATUS_FILE", str(tmp_path / "status.json"))  # never the real /run/smart_speaker
    data_path = str(tmp_path / ("server_data.json" if kind == "json" else "server_data.db"))
    from storage import SqliteStore
    store = (JsonStore if kind == "json" else SqliteStore)(data_path, today=lambda: "2026-10-03")
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "DATA_FILE", str(tmp_path / "server_data.json"))
    monkeypatch.setattr(server_module, "UPLOADS_DIR", str(uploads))
    monkeypatch.setattr(server_module, "OLD_TAGS_FILE", str(tmp_path / "tags.json"))
    # Never ask the real network whether the setup hotspot is up (that runs iwgetid/nmcli); tests flip this
    wifi = {"setup_mode": False}
    monkeypatch.setattr(server_module, "is_ap_mode", lambda: wifi["setup_mode"])
    monkeypatch.delenv("SPEAKER_CORS_ORIGIN", raising=False)
    httpd = server_module.ThreadPoolHTTPServer(("127.0.0.1", 0), server_module.SpeakerHandler, max_workers=2)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    client = Client("http://127.0.0.1:%d" % httpd.server_address[1])
    client.kind = kind
    client.wifi = wifi
    client.data_path = data_path
    client.module = server_module
    client.tmp = tmp_path
    yield client
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)
    for s in (store, server_module.store):
        if hasattr(s, "close"):
            s.close()


class Client:
    """A tiny HTTP client for the test server. Every call returns (status, parsed JSON or None)."""

    def __init__(self, base):
        self.base = base
        self.token = None  # sent as X-Speaker-Token when set

    def raw_call(self, method, path, body=None, raw=None, headers=None, token=True):
        """(status, response headers, parsed JSON or None)."""
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        sent = dict(headers or {})
        if token and self.token:
            sent.setdefault("X-Speaker-Token", self.token)
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=sent)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read()
                status, response_headers = response.status, response.headers
        except urllib.error.HTTPError as error:
            payload, status, response_headers = error.read(), error.code, error.headers
        try:
            parsed = json.loads(payload) if payload else None
        except ValueError:
            parsed = None
        return status, response_headers, parsed

    def call(self, method, path, body=None, raw=None, headers=None, token=True):
        status, _, parsed = self.raw_call(method, path, body, raw, headers, token)
        return status, parsed

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, body, **kw)

    def put(self, path, body=None, **kw):
        return self.call("PUT", path, body, **kw)

    def delete(self, path, **kw):
        return self.call("DELETE", path, **kw)
