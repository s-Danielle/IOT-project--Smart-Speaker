"""Who may change the speaker: the token, the exceptions, the size limits and the cross-site rule.

The rules themselves are plain functions. The server tests run a real server on this computer; to
play "another device on the network" they tell the server that the caller is not the speaker itself.
Nothing here runs a /debug command: refused requests don't run anything, and the one allowed
request used is for a route that does not exist.
"""

import http.client
import os
import stat

import pytest

from utils import access
from utils.access import ALWAYS, NEVER, UNLESS_SETUP_MODE, is_local_address, protection, token_matches
from utils.secrets_file import MIN_TOKEN_LENGTH, ensure_token, read_secret

# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method, path, expected", [
    # plain reads are open
    ("GET", "/status", NEVER), ("GET", "/health", NEVER), ("GET", "/chips", NEVER), ("GET", "/chips/lookup?uid=AA", NEVER),
    ("GET", "/library", NEVER), ("GET", "/settings/parental", NEVER), ("GET", "/usage/today", NEVER),
    ("GET", "/", NEVER), ("GET", "/index.html", NEVER), ("GET", "/main.dart.js", NEVER), ("GET", "/generate_204", NEVER),
    ("GET", "/chips/", NEVER),
    # anything that changes something needs the token
    ("POST", "/chips", ALWAYS), ("PUT", "/chips/chip1", ALWAYS), ("DELETE", "/chips/chip1", ALWAYS),
    ("DELETE", "/chips/chip1/assignment", ALWAYS), ("POST", "/library", ALWAYS), ("PUT", "/library/s1", ALWAYS),
    ("DELETE", "/library/s1", ALWAYS), ("PUT", "/settings/parental", ALWAYS), ("POST", "/usage/add", ALWAYS),
    ("POST", "/files", ALWAYS), ("PATCH", "/chips/chip1", ALWAYS),
    # all of /debug, even reads
    ("GET", "/debug/logs", ALWAYS), ("GET", "/debug/system", ALWAYS), ("GET", "/debug/i2c", ALWAYS),
    ("GET", "/debug/git-status", ALWAYS), ("GET", "/debug/speaker/status", ALWAYS),
    ("GET", "/debug/wifi/connections", ALWAYS), ("POST", "/debug/reboot", ALWAYS), ("POST", "/debug/git-pull", ALWAYS),
    ("POST", "/debug/speaker/restart", ALWAYS), ("POST", "/debug/wifi/forget", ALWAYS), ("POST", "/debug/wifi/ap-mode", ALWAYS),
    ("GET", "/debug", ALWAYS), ("GET", "/debug/", ALWAYS),
    # the WiFi setup works for a phone that has just joined the hotspot
    ("GET", "/wifi-setup", UNLESS_SETUP_MODE), ("POST", "/wifi-setup/connect", UNLESS_SETUP_MODE),
    ("POST", "/wifi-setup/connect?x=1", UNLESS_SETUP_MODE), ("GET", "/debug/wifi/status", UNLESS_SETUP_MODE),
    ("GET", "/debug/wifi/scan", UNLESS_SETUP_MODE), ("POST", "/debug/wifi/connect", UNLESS_SETUP_MODE),
    ("GET", "/debug/wifi/connect-status", UNLESS_SETUP_MODE),
])
def test_who_needs_the_token(method, path, expected):
    assert protection(method, path) == expected


def test_a_query_string_cannot_turn_a_protected_route_into_an_open_one():
    assert protection("POST", "/chips?x=/status") == ALWAYS
    assert protection("GET", "/debug/logs?/status") == ALWAYS
    # The door and the router must read the path the same way. Both use urlparse, so "//debug/logs"
    # (which urlparse reads as host "debug", path "/logs") is not a debug route for either of them.
    assert protection("GET", "//debug/logs") == NEVER and access.normalize("//debug/logs") == "/logs"


def test_only_the_setup_routes_are_open_in_setup_mode():
    open_in_setup = {p for p in access.SETUP_ROUTES}
    assert open_in_setup == {"/wifi-setup", "/wifi-setup/connect", "/debug/wifi/status", "/debug/wifi/scan",
                             "/debug/wifi/connect", "/debug/wifi/connect-status"}
    # not the dangerous ones: reboot, forget, disconnect, ap-mode, priority, logs, restart
    for route in ("/debug/reboot", "/debug/wifi/forget", "/debug/wifi/disconnect", "/debug/wifi/ap-mode",
                  "/debug/wifi/priority", "/debug/wifi/connections", "/debug/logs", "/debug/speaker/restart"):
        assert protection("POST", route) == ALWAYS


@pytest.mark.parametrize("address, expected", [
    ("127.0.0.1", True), ("127.1.2.3", True), ("::1", True), ("::ffff:127.0.0.1", True),
    ("192.168.1.20", False), ("10.0.0.5", False), ("192.168.4.2", False), ("8.8.8.8", False),
    ("::ffff:192.168.1.20", False), ("fe80::1", False), ("garbage", False), ("", False), ("localhost", False),
])
def test_which_callers_are_the_speaker_itself(address, expected):
    assert is_local_address(address) is expected


@pytest.mark.parametrize("supplied, expected, ok", [
    ("abc123def456ghij", "abc123def456ghij", True),
    ("abc123def456ghik", "abc123def456ghij", False),
    ("ABC123DEF456GHIJ", "abc123def456ghij", False),
    ("abc123def456ghi", "abc123def456ghij", False),
    ("abc123def456ghijX", "abc123def456ghij", False),
    ("", "abc123def456ghij", False),
    (None, "abc123def456ghij", False),
    ("abc123def456ghij", None, False),
    ("", "", False),  # no token set means nobody gets in by sending nothing
    (None, None, False),
    ("tökén-ünïcode", "tökén-ünïcode", True),
])
def test_the_token_comparison(supplied, expected, ok):
    assert token_matches(supplied, expected) is ok


# ---------------------------------------------------------------------------
# The SECRETS file
# ---------------------------------------------------------------------------

TEMPLATE_LIKE = '''# Smart Speaker - Secrets
WIFI_SSID="home"
WIFI_PASSWORD='pa ss=word'

# Remote debug token
DEBUG_TOKEN=""

AP_PASSWORD=""
'''


@pytest.fixture
def secrets_path(tmp_path):
    return str(tmp_path / "SECRETS")


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def test_reading_values_from_the_secrets_file(secrets_path):
    write(secrets_path, TEMPLATE_LIKE)
    assert read_secret(secrets_path, "WIFI_SSID") == "home"
    assert read_secret(secrets_path, "WIFI_PASSWORD") == "pa ss=word"
    assert read_secret(secrets_path, "DEBUG_TOKEN") == ""
    assert read_secret(secrets_path, "NOT_THERE") == ""
    assert read_secret(secrets_path + ".missing", "WIFI_SSID") == ""


def test_an_existing_token_is_kept(secrets_path):
    write(secrets_path, TEMPLATE_LIKE.replace('DEBUG_TOKEN=""', 'DEBUG_TOKEN="my-own-long-token"'))
    before = open(secrets_path).read()
    assert ensure_token(secrets_path) == ("my-own-long-token", False, None)
    assert open(secrets_path).read() == before


def test_a_new_token_replaces_the_empty_one_and_nothing_else_changes(secrets_path):
    write(secrets_path, TEMPLATE_LIKE)
    token, created, problem = ensure_token(secrets_path)
    assert created is True and problem is None
    assert len(token) == 16 and all(c.isalnum() or c in "-_" for c in token)
    assert read_secret(secrets_path, "DEBUG_TOKEN") == token
    assert open(secrets_path).read() == TEMPLATE_LIKE.replace('DEBUG_TOKEN=""', f'DEBUG_TOKEN="{token}"')


def test_a_token_that_is_too_short_counts_as_not_set(secrets_path):
    write(secrets_path, 'DEBUG_TOKEN="1234"\n')
    token, created, _ = ensure_token(secrets_path)
    assert created is True and token != "1234" and len(token) >= MIN_TOKEN_LENGTH
    assert open(secrets_path).read() == f'DEBUG_TOKEN="{token}"\n'


def test_a_file_without_the_key_gets_it_added(secrets_path):
    write(secrets_path, 'WIFI_SSID="home"')  # no trailing newline
    token, created, _ = ensure_token(secrets_path)
    assert open(secrets_path).read() == f'WIFI_SSID="home"\nDEBUG_TOKEN="{token}"\n'


def test_a_missing_file_is_created_for_its_owner_only(secrets_path):
    token, created, problem = ensure_token(secrets_path)
    assert created is True and problem is None and read_secret(secrets_path, "DEBUG_TOKEN") == token
    assert stat.S_IMODE(os.stat(secrets_path).st_mode) == 0o600


def test_the_files_permissions_are_kept(secrets_path):
    write(secrets_path, TEMPLATE_LIKE)
    os.chmod(secrets_path, 0o640)
    ensure_token(secrets_path)
    assert stat.S_IMODE(os.stat(secrets_path).st_mode) == 0o640


def test_as_root_the_file_stays_with_its_owner(secrets_path, monkeypatch):
    # The server runs as root; the speaker's user has to be able to read the token.
    write(secrets_path, TEMPLATE_LIKE)
    calls = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: calls.append((uid, gid)))
    ensure_token(secrets_path)
    info = os.stat(secrets_path)
    assert calls == [(info.st_uid, info.st_gid)]


def test_a_token_that_cannot_be_saved_is_reported_not_raised(tmp_path):
    token, created, problem = ensure_token(str(tmp_path / "no" / "such" / "folder" / "SECRETS"))
    assert created is True and len(token) == 16
    assert problem and "could not save" in problem
    assert os.listdir(tmp_path) == []


def test_no_temporary_file_is_left_behind(secrets_path, tmp_path):
    write(secrets_path, TEMPLATE_LIKE)
    ensure_token(secrets_path)
    assert os.listdir(tmp_path) == ["SECRETS"]


def test_two_new_tokens_are_different(tmp_path):
    first = ensure_token(str(tmp_path / "a"))[0]
    second = ensure_token(str(tmp_path / "b"))[0]
    assert first != second


# ---------------------------------------------------------------------------
# The server: playing "another device on the network"
# ---------------------------------------------------------------------------

TOKEN = "correct-horse-battery"


@pytest.fixture
def remote(api, monkeypatch):
    """The server believes every caller is another device, and knows the token."""
    monkeypatch.setattr(api.module, "API_TOKEN", TOKEN)
    monkeypatch.setattr(api.module, "is_local_address", lambda address: False)
    api.token = None
    return api


def test_reads_are_open_to_anyone(remote):
    for path in ("/status", "/chips", "/library", "/settings/parental", "/usage/today", "/chips/lookup?uid=AA"):
        assert remote.get(path)[0] in (200, 404), path  # 404 only for the unknown chip
    assert remote.get("/health")[0] in (200, 503)


def test_odd_spellings_of_a_debug_path_are_not_debug_routes_and_run_nothing(remote):
    for path in ("//debug/logs", "/debug%2Flogs", "/%64ebug/logs", "/./debug/logs", "/debug/../debug/logs"):
        status, body = remote.get(path)
        # the web app's page (it answers unknown paths with the app shell), a 404, or the door: never the logs
        assert status in (200, 404, 503, 401), path
        assert body is None or "lines" not in body and "logs" not in body, path


def test_the_web_app_is_open_to_anyone(remote):
    assert remote.get("/")[0] != 401
    assert remote.get("/index.html")[0] != 401


def test_changes_without_the_token_are_refused_and_change_nothing(remote):
    before = (remote.get("/chips")[1], remote.get("/library")[1], remote.get("/settings/parental")[1], remote.get("/usage/today")[1])
    attempts = [
        ("POST", "/chips", {"uid": "AA11"}), ("PUT", "/chips/x", {"name": "n"}), ("DELETE", "/chips/x", None),
        ("DELETE", "/chips/x/assignment", None), ("POST", "/library", {"name": "n", "uri": "u"}),
        ("PUT", "/library/song001", {"name": "hacked"}), ("DELETE", "/library/song001", None),
        ("PUT", "/settings/parental", {"enabled": False, "volume_limit": 100}), ("POST", "/usage/add", {"seconds": 99}),
        ("POST", "/files", None),
    ]
    for method, path, body in attempts:
        status, answer = remote.call(method, path, body)
        assert status == 401, (method, path)
        assert "X-Speaker-Token" in answer["error"]
    after = (remote.get("/chips")[1], remote.get("/library")[1], remote.get("/settings/parental")[1], remote.get("/usage/today")[1])
    assert after == before


def test_changes_with_the_token_work(remote):
    remote.token = TOKEN
    status, chip = remote.post("/chips", {"uid": "AA11"})
    assert status == 201
    assert remote.put("/chips/" + chip["id"], {"name": "Bedtime"})[0] == 200
    assert remote.post("/usage/add", {"seconds": 5})[0] == 200
    assert remote.put("/settings/parental", {"volume_limit": 40})[1]["volume_limit"] == 40
    assert remote.delete("/chips/" + chip["id"])[0] == 204


@pytest.mark.parametrize("wrong", ["", "wrong", TOKEN.upper(), TOKEN[:-1], TOKEN + "x", "x" + TOKEN, "Bearer " + TOKEN])
def test_a_wrong_token_is_refused(remote, wrong):
    remote.token = wrong or None
    assert remote.post("/chips", {"uid": "AA11"})[0] == 401
    assert remote.get("/chips")[1] == []


def test_the_token_in_the_url_or_the_body_does_not_count(remote):
    assert remote.post("/chips?token=" + TOKEN, {"uid": "AA11", "token": TOKEN})[0] == 401
    assert remote.post("/chips", {"uid": "AA11"}, headers={"Authorization": "Bearer " + TOKEN})[0] == 401


def test_no_token_set_on_the_speaker_means_nobody_gets_in(remote, monkeypatch):
    monkeypatch.setattr(remote.module, "API_TOKEN", None)
    assert remote.post("/chips", {"uid": "AA11"})[0] == 401
    remote.token = ""
    assert remote.post("/chips", {"uid": "AA11"}, headers={"X-Speaker-Token": ""})[0] == 401


def test_everything_under_debug_needs_the_token_even_reads(remote):
    for method, path in [("GET", "/debug/logs"), ("GET", "/debug/system"), ("GET", "/debug/i2c"), ("GET", "/debug/git-status"),
                         ("GET", "/debug/speaker/status"), ("GET", "/debug/wifi/connections"), ("POST", "/debug/reboot"),
                         ("POST", "/debug/git-pull"), ("POST", "/debug/speaker/restart"), ("POST", "/debug/daemon-reload"),
                         ("POST", "/debug/wifi/forget"), ("POST", "/debug/wifi/disconnect"), ("POST", "/debug/wifi/ap-mode")]:
        assert remote.call(method, path)[0] == 401, (method, path)  # and nothing was run


def test_with_the_token_a_debug_request_gets_past_the_door(remote):
    remote.token = TOKEN
    # routes that do not exist, so nothing is run: an answer that is not 401 shows the door let it in
    assert remote.get("/debug/no-such-thing")[0] != 401  # (the web app's page: it answers unknown paths with the app shell)
    assert remote.post("/debug/no-such-thing")[0] == 404


def test_the_hand_started_second_controller_is_gone(remote):
    remote.token = TOKEN
    assert not hasattr(remote.module, "debug_run_main")
    assert remote.post("/debug/run-main")[0] == 404


def test_the_speaker_itself_needs_no_token(api):
    # The controller and the health monitor call the server on localhost without a token.
    assert api.token is None
    assert api.post("/chips", {"uid": "AA11"})[0] == 201
    assert api.post("/usage/add", {"seconds": 3})[0] == 200
    assert api.delete("/chips/%s/assignment" % api.get("/chips")[1][0]["id"])[0] == 204


def test_setup_mode_opens_only_the_setup_routes(remote):
    remote.wifi["setup_mode"] = False
    assert remote.get("/debug/wifi/connect-status")[0] == 401
    assert remote.post("/wifi-setup/connect", raw=b"ssid=x", headers={"Content-Type": "application/x-www-form-urlencoded"})[0] == 401
    remote.wifi["setup_mode"] = True
    assert remote.get("/debug/wifi/connect-status")[0] == 200  # a phone that has just joined the hotspot
    for method, path in [("POST", "/debug/reboot"), ("POST", "/debug/wifi/forget"), ("POST", "/debug/wifi/ap-mode"),
                         ("GET", "/debug/logs"), ("GET", "/debug/wifi/connections"), ("POST", "/chips"), ("PUT", "/settings/parental")]:
        assert remote.call(method, path)[0] == 401, (method, path)  # even then


def test_refusals_are_logged_once_not_for_every_request(remote, monkeypatch):
    lines = []
    monkeypatch.setattr(remote.module, "log", lambda message, category="INFO": lines.append((category, message)))
    monkeypatch.setattr(remote.module, "_refusal_log", {})
    for _ in range(8):
        remote.post("/chips", {"uid": "AA11"})
    security = [m for c, m in lines if "[SECURITY]" in m]
    assert len(security) == 1 and "missing token" in security[0]
    assert TOKEN not in " ".join(m for _, m in lines)


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
        "Access-Control-Request-Headers": "x-speaker-token"})
    assert status == 403 and "Access-Control-Allow-Origin" not in headers


def test_a_preflight_without_an_origin_is_just_answered(api):
    status, headers, _ = api.raw_call("OPTIONS", "/chips")
    assert status == 204 and "Access-Control-Allow-Origin" not in headers


def test_a_developer_can_allow_exactly_one_origin(api, monkeypatch):
    monkeypatch.setenv("SPEAKER_CORS_ORIGIN", "http://localhost:5000")
    status, headers, _ = api.raw_call("OPTIONS", "/chips", headers={"Origin": "http://localhost:5000"})
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5000"
    assert "X-Speaker-Token" in headers["Access-Control-Allow-Headers"]
    status, headers, _ = api.raw_call("GET", "/chips", headers={"Origin": "http://localhost:5000"})
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5000"
    for other in ("http://localhost:5001", "http://evil.example", "null"):
        status, headers, _ = api.raw_call("GET", "/chips", headers={"Origin": other})
        assert "Access-Control-Allow-Origin" not in headers, other
        assert api.raw_call("OPTIONS", "/chips", headers={"Origin": other})[0] == 403


# ---------------------------------------------------------------------------
# Making the token at start-up
# ---------------------------------------------------------------------------


def test_the_server_makes_its_token_at_start_and_never_logs_it(api, monkeypatch, tmp_path):
    path = str(tmp_path / "SECRETS")
    monkeypatch.setattr(api.module, "SECRETS_PATH", path)
    monkeypatch.setattr(api.module, "API_TOKEN", None)
    lines = []
    monkeypatch.setattr(api.module, "log", lambda message, category="INFO": lines.append(message))
    api.module.start_security()
    token = read_secret(path, "DEBUG_TOKEN")
    assert len(token) == 16 and api.module.API_TOKEN == token
    assert any("new API token was created" in l for l in lines)
    assert token not in " ".join(lines)
    lines.clear()
    api.module.start_security()  # the second start uses the same token
    assert api.module.API_TOKEN == token and any("loaded" in l for l in lines)


def test_if_the_token_cannot_be_saved_remote_changes_are_refused_and_it_says_so(api, monkeypatch, tmp_path):
    monkeypatch.setattr(api.module, "SECRETS_PATH", str(tmp_path / "nowhere" / "SECRETS"))
    lines = []
    monkeypatch.setattr(api.module, "log", lambda message, category="INFO": lines.append((category, message)))
    api.module.start_security()
    assert api.module.API_TOKEN  # a token for this run that nobody can read
    assert any(c == "ERROR" and "could not save" in m for c, m in lines)
