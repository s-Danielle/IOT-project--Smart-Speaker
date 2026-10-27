"""Request size limits and the cross-site (CORS) answers.

There is no password: anyone on the network may use the API. The server tests run a real server on the
development machine. Nothing here runs a /debug command: the requests used are for a route that does
not exist, or are refused before anything runs.
"""

import http.client
import os

import pytest


def test_the_hand_started_second_controller_is_gone(api):
    assert not hasattr(api.module, "debug_run_main")
    assert api.post("/debug/run-main")[0] == 404


# ---------------------------------------------------------------------------
# Size limits
# ---------------------------------------------------------------------------


def test_a_json_body_that_is_too_big_is_refused_without_being_read(api):
    big = b'{"name": "' + b"x" * (api.module.MAX_JSON_BYTES + 10) + b'", "uri": "u"}'
    assert api.post("/library", raw=big)[0] == 413
    assert len(api.get("/library")[1]) == 2


def test_a_json_body_just_under_the_limit_is_fine(api):
    name = "x" * 1000
    assert api.post("/library", {"name": name, "uri": "u"})[0] == 201


def test_an_upload_that_is_too_big_is_refused_and_nothing_is_saved(api, monkeypatch):
    monkeypatch.setattr(api.module, "MAX_UPLOAD_BYTES", 500)
    boundary = "xBx"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.mp3"\r\n\r\n').encode() + b"A" * 2000 + f"\r\n--{boundary}--\r\n".encode()
    assert api.post("/files", raw=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})[0] == 413
    assert os.listdir(api.tmp / "uploads") == []
    assert len(api.get("/library")[1]) == 2


def test_the_wifi_form_has_a_small_limit(api, monkeypatch):
    body = b"ssid=x&password=" + b"p" * (api.module.MAX_FORM_BYTES + 5)
    status, _ = api.post("/wifi-setup/connect", raw=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert status == 413


@pytest.mark.parametrize("length", ["abc", "-5", "1e3", ""])
def test_a_content_length_that_makes_no_sense_is_a_bad_request(api, length):
    host, port = api.base.split("//")[1].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    conn.putrequest("POST", "/library")
    conn.putheader("Content-Length", length)
    conn.putheader("Content-Type", "application/json")
    conn.endheaders()
    response = conn.getresponse()
    status = response.status
    conn.close()
    assert status == 400 or (length == "" and status in (201, 400))
    assert len(api.get("/library")[1]) == 2


def test_the_limits_apply_to_the_speaker_itself_too(api):
    assert api.post("/library", raw=b"x" * (api.module.MAX_JSON_BYTES + 1))[0] == 413


# ---------------------------------------------------------------------------
# Cross-site requests
# ---------------------------------------------------------------------------


def test_no_response_lets_another_website_read_it(api):
    for path in ("/status", "/chips", "/library", "/settings/parental", "/health"):
        status, headers, _ = api.raw_call("GET", path, headers={"Origin": "http://evil.example"})
        assert "Access-Control-Allow-Origin" not in headers, path
    status, headers, _ = api.raw_call("POST", "/chips", {"uid": "AA11"}, headers={"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in headers


def test_a_cross_site_preflight_is_refused(api):
    status, headers, body = api.raw_call("OPTIONS", "/chips", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert status == 403 and "Access-Control-Allow-Origin" not in headers


def test_a_preflight_without_an_origin_is_just_answered(api):
    status, headers, _ = api.raw_call("OPTIONS", "/chips")
    assert status == 204 and "Access-Control-Allow-Origin" not in headers


def test_a_developer_can_allow_exactly_one_origin(api, monkeypatch):
    monkeypatch.setenv("SPEAKER_CORS_ORIGIN", "http://localhost:5000")
    status, headers, _ = api.raw_call("OPTIONS", "/chips", headers={"Origin": "http://localhost:5000"})
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5000"
    assert headers["Access-Control-Allow-Headers"] == "Content-Type"
    status, headers, _ = api.raw_call("GET", "/chips", headers={"Origin": "http://localhost:5000"})
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5000"
    for other in ("http://localhost:5001", "http://evil.example", "null"):
        status, headers, _ = api.raw_call("GET", "/chips", headers={"Origin": other})
        assert "Access-Control-Allow-Origin" not in headers, other
        assert api.raw_call("OPTIONS", "/chips", headers={"Origin": other})[0] == 403


# ---------------------------------------------------------------------------
# git run from the app's Developer Tools
# ---------------------------------------------------------------------------


def test_git_is_run_as_the_owner_of_the_program_folder_when_the_server_is_root(api):
    command = api.module.git_command(["pull"], folder="/home/iot-proj/repo", euid=0, owner_of=lambda path: "iot-proj")
    assert command == ["sudo", "-u", "iot-proj", "-H", "git", "pull"]


def test_git_is_run_plainly_by_a_normal_user_or_when_root_owns_the_folder(api):
    assert api.module.git_command(["status"], folder="/x", euid=1000, owner_of=lambda p: "iot-proj") == ["git", "status"]
    assert api.module.git_command(["status"], folder="/x", euid=0, owner_of=lambda p: "root") == ["git", "status"]


def test_git_falls_back_to_plain_when_the_owner_cannot_be_found(api):
    def unknown(path):
        raise KeyError("no such user")

    assert api.module.git_command(["pull"], folder="/x", euid=0, owner_of=unknown) == ["git", "pull"]


def test_all_three_git_calls_use_that_command(api):
    import inspect
    source = inspect.getsource(api.module)
    assert "['git'," not in source.replace("['git'] + list(args)", "")


# ---------------------------------------------------------------------------
# A bad request body is a 400 on every route, never a dropped connection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2]", b'"text"', b"null", b"42", b"\xff\xfe"])
@pytest.mark.parametrize("method, path", [
    ("POST", "/chips"), ("POST", "/library"), ("POST", "/usage/add"), ("PUT", "/settings/parental"),
    ("PUT", "/chips/x"), ("PUT", "/library/x"),
])
def test_a_body_that_is_not_a_json_object_is_a_400_on_every_data_route(api, method, path, body):
    status, answer = api.call(method, path, raw=body)
    assert status == 400 and "error" in answer
    assert api.get("/status")[0] == 200  # and the server is fine


@pytest.mark.parametrize("path", ["/debug/wifi/forget", "/debug/wifi/connect", "/debug/wifi/priority", "/debug/wifi/ap-mode"])
def test_a_bad_body_to_a_debug_route_is_a_400_and_runs_nothing(api, path):
    status, answer = api.post(path, raw=b"{broken")
    assert status == 400 and "error" in answer  # the body is read before anything is run


def test_connections_that_send_nothing_do_not_block_the_server(api, monkeypatch):
    """Browsers open spare connections and never use them. Each used to hold a worker for ever."""
    import socket
    import time
    monkeypatch.setattr(api.module.SpeakerHandler, "timeout", 0.5)
    port = int(api.base.rsplit(":", 1)[1])
    idle = [socket.create_connection(("127.0.0.1", port)) for _ in range(8)]  # more than there are workers
    try:
        time.sleep(0.1)
        start = time.monotonic()
        status, _ = api.get("/status")
        assert status == 200
        assert time.monotonic() - start < 5
    finally:
        for sock in idle:
            sock.close()


def test_an_idle_connection_is_given_up_after_a_while(server_module):
    # None (the library's default) means for ever
    assert server_module.SpeakerHandler.timeout is not None
    assert 0 < server_module.SpeakerHandler.timeout <= 30


def test_without_a_deployed_web_app_the_server_says_so(api, monkeypatch, tmp_path):
    """The repo no longer carries a placeholder index.html, so the server has to explain it itself."""
    empty = tmp_path / "no_web_app"
    empty.mkdir()
    monkeypatch.setattr(api.module, "WEB_APP_DIR", str(empty))
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(api.base + "/", timeout=5)
        raise AssertionError("expected a 503")
    except urllib.error.HTTPError as error:
        assert error.code == 503
        assert b"Web app not deployed" in error.read()
