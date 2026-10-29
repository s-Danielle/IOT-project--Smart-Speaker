"""WiFi setup: a slow start must not leave the speaker in setup mode for ever, and a network that
goes away (or never comes) must bring the setup hotspot back.

NetworkManager, iwgetid and iw are all replaced by fakes here. Nothing touches the real network.
"""

import subprocess

import pytest

import fakes
import hardware.wifi_manager as wifi_manager
from hardware.wifi_manager import WiFiManager
from wifi_provisioner import AP_RETRY_INTERVAL, AP_RETRY_WAIT, NO_NETWORK_GRACE, WATCH_INTERVAL, WiFiProvisioner


# ---------------------------------------------------------------------------
# The provisioner, with a fake clock and a fake WiFi
# ---------------------------------------------------------------------------


class Clock:
    """Fake time: sleep() moves it, then runs on_tick(t) so a test can say what happens when."""

    def __init__(self, limit=3600):
        self.t = 0.0
        self.limit = limit
        self.on_tick = None

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        if self.on_tick:
            self.on_tick(self.t)
        if self.t > self.limit:
            raise TimeoutError("the provisioner did not finish (that is the test's way of stopping a loop)")


class FakeWiFi:
    def __init__(self):
        self.connected = False  # is there a saved network to join?
        self.ap_up = False
        self.clients = False  # is someone connected to the hotspot?
        self.responder = False  # is the port-80 helper of the hotspot running (in the provisioner's program)?
        self.calls = []
        self.music_restarts = []  # what each restart of the music server returned (kept here so build() stays small)

    def is_connected(self):
        return self.connected and not self.ap_up

    def is_online(self):
        return self.is_connected()

    def get_current_ssid(self):
        if self.ap_up:
            return wifi_manager.AP_SSID
        return "Home" if self.connected else ""

    def start_ap(self):
        self.calls.append("start_ap")
        self.ap_up = True
        self.responder = True
        return True

    def stop_ap(self):
        self.calls.append("stop_ap")
        self.ap_up = False
        self.responder = False
        return True

    def stop_captive_responder(self):
        self.responder = False

    def reconnect(self):
        self.calls.append("reconnect")
        return True

    def has_ap_clients(self):
        return self.clients


def build(limit=3600, portal_busy=lambda: False, music_restart_works=True):
    clock, wifi, led = Clock(limit), FakeWiFi(), fakes.CallLog()

    def restart_music():
        wifi.music_restarts.append(music_restart_works)
        return music_restart_works

    provisioner = WiFiProvisioner(wifi=wifi, led=led, clock=clock.now, sleep=clock.sleep,
                                  portal_busy=portal_busy, restart_music=restart_music)
    return provisioner, wifi, clock, led


def test_a_normal_boot_never_starts_the_hotspot():
    provisioner, wifi, clock, led = build()
    wifi.connected = True
    provisioner.boot()
    assert wifi.calls == []
    assert "connected" in led.names()


def test_wifi_that_arrives_within_the_wait_never_starts_the_hotspot():
    provisioner, wifi, clock, led = build()
    clock.on_tick = lambda t: setattr(wifi, "connected", t >= 10)
    provisioner.boot()
    assert wifi.calls == []


def test_the_music_server_is_restarted_once_the_speaker_has_a_network():
    # Mopidy logs in to Spotify only while it starts, and at boot it starts before the network
    # is there. Without this restart every Spotify song fails until somebody restarts it by hand.
    provisioner, wifi, clock, led = build()
    wifi.connected = True
    provisioner.boot()
    assert wifi.music_restarts == [True]


def test_a_setup_through_the_hotspot_restarts_the_music_server_too():
    # The worst case: the network arrives minutes after Mopidy started, when somebody has
    # just typed the password into the setup page.
    provisioner, wifi, clock, led = build()
    clock.on_tick = lambda t: setattr(wifi, "connected", t >= 100)
    provisioner.boot()
    assert wifi.music_restarts == [True]  # once, at the end of setup mode


def test_a_short_break_in_the_network_leaves_the_music_server_alone():
    # NetworkManager gets a blip back by itself. A restart here would cut off whatever is playing.
    provisioner, wifi, clock, led = build(limit=NO_NETWORK_GRACE)
    wifi.connected = True
    clock.on_tick = lambda t: setattr(wifi, "connected", not (20 <= t < 40))
    with pytest.raises(TimeoutError):
        provisioner.watch()
    assert wifi.music_restarts == []


def test_a_music_server_that_will_not_restart_does_not_stop_the_speaker():
    provisioner, wifi, clock, led = build(music_restart_works=False)
    wifi.connected = True
    provisioner.boot()  # says so in the log and goes on
    assert wifi.music_restarts == [False]


def test_no_wifi_at_boot_starts_the_hotspot():
    provisioner, wifi, clock, led = build(limit=NO_NETWORK_GRACE + 20)
    with pytest.raises(TimeoutError):
        provisioner.boot()
    assert wifi.calls == ["start_ap"]
    assert "ap_mode" in led.names()


def test_the_speaker_gets_out_of_setup_mode_when_the_wifi_comes_back():
    # Sep 5: the router was not ready in time, the speaker opened its hotspot, and then
    # sat there with no internet until somebody rebooted it.
    provisioner, wifi, clock, led = build()
    clock.on_tick = lambda t: setattr(wifi, "connected", t >= 100)  # the router comes up at 100 s
    provisioner.boot()  # must come back by itself
    assert wifi.calls == ["start_ap", "stop_ap", "reconnect"]
    assert led.names()[-1] == "connected"
    assert clock.t < NO_NETWORK_GRACE + AP_RETRY_INTERVAL + AP_RETRY_WAIT + 10


def test_if_the_wifi_is_still_down_the_hotspot_comes_back():
    provisioner, wifi, clock, led = build(limit=NO_NETWORK_GRACE + 3 * AP_RETRY_INTERVAL)
    with pytest.raises(TimeoutError):
        provisioner.boot()
    assert wifi.calls.count("start_ap") >= 3  # up, down for a retry, up again, ...
    assert wifi.calls.count("stop_ap") >= 2
    assert wifi.ap_up or wifi.calls[-1] in ("stop_ap", "reconnect")  # it is never left dead for long


def test_nobody_is_thrown_off_the_hotspot_while_setting_it_up():
    provisioner, wifi, clock, led = build(limit=NO_NETWORK_GRACE + 3 * AP_RETRY_INTERVAL)
    wifi.clients = True
    with pytest.raises(TimeoutError):
        provisioner.boot()
    assert wifi.calls == ["start_ap"]  # never stopped


def test_setting_up_through_the_portal_still_works():
    provisioner, wifi, clock, led = build()

    def server_connects(t):
        if t >= 60:  # the portal joined a network and tore the hotspot down
            wifi.ap_up = False
            wifi.connected = True

    clock.on_tick = server_connects
    provisioner.boot()
    assert "stop_ap" not in wifi.calls  # the provisioner did not need to do anything
    assert led.names()[-1] == "connected"


# ---------------------------------------------------------------------------
# Once online, the provisioner keeps watching (the router moved, replaced or switched off)
# ---------------------------------------------------------------------------


def offline_between(wifi, start, end):
    """on_tick for a clock: the network is gone from `start` until `end` (seconds)."""
    return lambda t: setattr(wifi, "connected", not (start <= t < end))


def test_the_provisioner_keeps_running_after_a_normal_boot():
    provisioner, wifi, clock, led = build(limit=3600)
    wifi.connected = True
    with pytest.raises(TimeoutError):  # it never returns by itself: it watches the network
        provisioner.run()
    assert wifi.calls == []


def test_a_short_break_in_the_network_is_left_to_networkmanager():
    provisioner, wifi, clock, led = build(limit=600)
    wifi.connected = True
    clock.on_tick = offline_between(wifi, 100, 100 + NO_NETWORK_GRACE - 2 * WATCH_INTERVAL)
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls == []


def test_no_network_for_a_minute_opens_the_setup_hotspot():
    provisioner, wifi, clock, led = build(limit=1000)
    wifi.connected = True
    opened = []
    clock.on_tick = lambda t: (setattr(wifi, "connected", t < 200), opened.append(t) if wifi.ap_up and not opened else None)
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls[0] == "start_ap"
    assert "ap_mode" in led.names()
    # it waited the whole grace (not less), and did not wait much longer
    assert 200 + NO_NETWORK_GRACE <= opened[0] <= 200 + NO_NETWORK_GRACE + 2 * WATCH_INTERVAL


def test_the_speaker_comes_back_to_the_watch_after_the_user_sets_up_a_new_network():
    provisioner, wifi, clock, led = build(limit=1500)
    wifi.connected = True
    done = {}  # when the user finished setting up
    starts = []  # when the hotspot came up

    real_start_ap = wifi.start_ap

    def start_ap():
        starts.append(clock.t)
        return real_start_ap()

    wifi.start_ap = start_ap

    def tick(t):
        if "at" not in done:
            wifi.connected = t < 200  # the router is gone
            if wifi.ap_up and t >= 400:  # a user joined the hotspot and the portal joined a new network
                wifi.ap_up = False
                wifi.connected = True
                done["at"] = t
        elif t >= 800:
            wifi.connected = False  # and later that router goes too

    clock.on_tick = tick
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert [t for t in starts if t < done["at"]]  # the first loss opened the hotspot
    between = [t for t in starts if done["at"] < t < 800]
    assert between == []  # online again: the hotspot stayed off
    assert [t for t in starts if t >= 800 + NO_NETWORK_GRACE]  # the second loss opened it again


def test_the_port_80_helper_is_stopped_when_setup_is_done():
    # The helper that makes phones open the setup page lives in the provisioner's program. The server
    # takes the hotspot down, so unless the provisioner stops the helper it keeps answering on port 80.
    provisioner, wifi, clock, led = build(limit=2000)
    wifi.connected = True
    seen = {}

    def tick(t):
        if t >= 200 and "joined" not in seen:
            wifi.connected = False
        if wifi.ap_up and t >= 400:
            wifi.ap_up = False  # the server's doing; wifi.responder stays on, as in real life
            wifi.connected = True
            seen["joined"] = t
        if "joined" in seen and t >= seen["joined"] + 30:
            seen.setdefault("responder_30s_later", wifi.responder)

    clock.on_tick = tick
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert seen["responder_30s_later"] is False


def test_no_network_while_the_setup_page_joins_one_does_not_count():
    # Somebody changed network through the app: the speaker is offline on purpose for a while.
    busy = {"now": False}
    provisioner, wifi, clock, led = build(limit=1000, portal_busy=lambda: busy["now"])
    wifi.connected = True

    def tick(t):
        wifi.connected = not (100 <= t < 400)
        busy["now"] = 100 <= t < 400

    clock.on_tick = tick
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls == []


def test_a_hotspot_that_is_already_up_is_not_restarted():
    # The developer tools can start the hotspot by hand. Starting it again throws its clients off.
    provisioner, wifi, clock, led = build(limit=1000)
    wifi.connected = True
    clock.on_tick = lambda t: setattr(wifi, "ap_up", t >= 100) or setattr(wifi, "clients", True)
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls == []


# ---------------------------------------------------------------------------
# WiFiManager: finding the tools and reading the network name
# ---------------------------------------------------------------------------


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


@pytest.fixture
def interface(monkeypatch):
    monkeypatch.setattr(wifi_manager, "_wifi_interface", "wlan0")


def test_a_tool_in_usr_sbin_is_found_although_it_is_not_on_the_users_path(monkeypatch):
    # iwgetid is in /usr/sbin, which a normal user's PATH does not include.
    def which(name, path=None):
        return "/usr/sbin/iwgetid" if path and "/usr/sbin" in path else None

    monkeypatch.setattr(wifi_manager.shutil, "which", which)
    assert wifi_manager.find_tool("iwgetid") == "/usr/sbin/iwgetid"


def test_the_ssid_comes_from_iwgetid(monkeypatch):
    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: "/usr/sbin/" + name)
    monkeypatch.setattr(wifi_manager.subprocess, "run", lambda cmd, **kw: completed("Home\n"))
    assert WiFiManager.get_current_ssid() == "Home"
    assert WiFiManager.is_connected() is True


def test_the_setup_hotspot_does_not_count_as_connected(monkeypatch):
    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: "/usr/sbin/" + name)
    monkeypatch.setattr(wifi_manager.subprocess, "run", lambda cmd, **kw: completed(wifi_manager.AP_SSID + "\n"))
    assert WiFiManager.is_connected() is False


def test_without_iwgetid_networkmanager_is_asked_instead(monkeypatch):
    def run(cmd, **kw):
        assert cmd[0] == "nmcli"
        # a read-only lookup: it must not start a scan (that can drop the setup hotspot's clients)
        assert cmd[-2:] == ["--rescan", "no"]
        return completed("no:Cafe\nyes:Home\\:5G\nno:Other\n")

    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: None)
    monkeypatch.setattr(wifi_manager.subprocess, "run", run)
    assert WiFiManager.get_current_ssid() == "Home:5G"  # the escaped colon is understood


def test_a_crashing_iwgetid_does_not_crash_the_wifi_service(monkeypatch):
    def run(cmd, **kw):
        if cmd[0].endswith("iwgetid"):
            raise FileNotFoundError("gone")
        return completed("yes:Home\n")

    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: "/usr/sbin/" + name)
    monkeypatch.setattr(wifi_manager.subprocess, "run", run)
    assert WiFiManager.get_current_ssid() == "Home"


def test_no_network_at_all_gives_an_empty_name(monkeypatch):
    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: None)
    monkeypatch.setattr(wifi_manager.subprocess, "run", lambda cmd, **kw: completed("no:Other\n"))
    assert WiFiManager.get_current_ssid() == ""
    assert WiFiManager.is_connected() is False


STATION_DUMP = "Station 3c:22:fb:12:34:56 (on wlan0)\n\tinactive time:\t120 ms\n\trx bytes:\t5120\n"


def test_clients_on_the_hotspot_are_seen(monkeypatch, interface):
    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: "/usr/sbin/" + name)
    monkeypatch.setattr(wifi_manager.subprocess, "run", lambda cmd, **kw: completed(STATION_DUMP))
    assert WiFiManager.has_ap_clients() is True


def test_an_empty_hotspot_has_no_clients(monkeypatch, interface):
    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: "/usr/sbin/" + name)
    monkeypatch.setattr(wifi_manager.subprocess, "run", lambda cmd, **kw: completed(""))
    assert WiFiManager.has_ap_clients() is False


def test_no_iw_means_no_clients_rather_than_a_crash(monkeypatch, interface):
    monkeypatch.setattr(wifi_manager, "find_tool", lambda name: None)
    assert WiFiManager.has_ap_clients() is False


# ---------------------------------------------------------------------------
# The retry must not fight the setup page
# ---------------------------------------------------------------------------


def test_the_retry_waits_while_the_setup_page_is_joining_a_network():
    # A user submitted the form: the server dropped the hotspot to join their network, so no client is
    # attached any more. The retry timer must not tear the hotspot down or bring it back in that window.
    busy = {"now": True}
    retry_at = NO_NETWORK_GRACE + AP_RETRY_INTERVAL  # the hotspot starts after the grace, the first retry is due one interval later
    provisioner, wifi, clock, led = build(limit=retry_at + 30, portal_busy=lambda: busy["now"])
    clock.on_tick = lambda t: busy.update(now=t < retry_at + 10)
    with pytest.raises(TimeoutError):
        provisioner.boot()
    assert wifi.calls == ["start_ap"]  # no stop_ap, no reconnect, no second start_ap while it was busy


def test_the_retry_goes_ahead_once_the_setup_page_is_done():
    provisioner, wifi, clock, led = build(portal_busy=lambda: False)
    clock.on_tick = lambda t: setattr(wifi, "connected", t >= 100)
    provisioner.boot()
    assert wifi.calls == ["start_ap", "stop_ap", "reconnect"]


@pytest.mark.parametrize("answer, expected", [
    (b'{"state": "connecting", "ssid": "x"}', True),
    (b'{"state": "idle"}', False),
    (b'{"state": "connected"}', False),
    (b'{"state": "failed"}', False),
    (b"not json", False),
    (b"[]", False),
])
def test_asking_the_server_whether_the_portal_is_busy(monkeypatch, answer, expected):
    import io
    import urllib.request
    import wifi_provisioner

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    requested = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0: requested.append(url) or Reply(answer))
    assert wifi_provisioner.portal_is_connecting() is expected
    assert requested == ["http://localhost:8080/debug/wifi/connect-status"]


def test_a_server_that_does_not_answer_means_nobody_is_using_the_portal(monkeypatch):
    import urllib.request
    import wifi_provisioner

    def refuse(url, timeout=0):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert wifi_provisioner.portal_is_connecting() is False


# ---------------------------------------------------------------------------
# "Online" means an address as well as a network name
# ---------------------------------------------------------------------------


def test_a_network_without_an_address_is_not_online(monkeypatch):
    monkeypatch.setattr(WiFiManager, "get_current_ssid", staticmethod(lambda: "Home"))
    monkeypatch.setattr(WiFiManager, "get_ip_address", staticmethod(lambda: None))
    assert WiFiManager.is_connected() is True
    assert WiFiManager.is_online() is False


def test_a_network_with_an_address_is_online(monkeypatch):
    monkeypatch.setattr(WiFiManager, "get_current_ssid", staticmethod(lambda: "Home"))
    monkeypatch.setattr(WiFiManager, "get_ip_address", staticmethod(lambda: "192.168.1.20"))
    assert WiFiManager.is_online() is True


def test_the_setup_hotspot_is_not_online_even_with_its_own_address(monkeypatch):
    monkeypatch.setattr(WiFiManager, "get_current_ssid", staticmethod(lambda: wifi_manager.AP_SSID))
    monkeypatch.setattr(WiFiManager, "get_ip_address", staticmethod(lambda: wifi_manager.AP_IP))
    assert WiFiManager.is_online() is False


def test_the_speakers_address_on_a_home_network_follows_its_hostname(monkeypatch):
    monkeypatch.setattr(wifi_manager.socket, "gethostname", lambda: "kitchen")
    assert wifi_manager.speaker_home_url() == "http://kitchen.local:8080"
    monkeypatch.setattr(wifi_manager.socket, "gethostname", lambda: "kitchen.fritz.box")
    assert wifi_manager.speaker_home_url() == "http://kitchen.local:8080"  # only the first part is the mDNS name
    monkeypatch.setattr(wifi_manager.socket, "gethostname", lambda: "")
    assert wifi_manager.speaker_home_url() == "http://rpi2.local:8080"


def test_the_network_list_page_shows_the_address_to_copy(monkeypatch):
    monkeypatch.setattr(wifi_manager.socket, "gethostname", lambda: "kitchen")
    page = wifi_manager.render_network_list_html([{"ssid": "Home", "signal": 80, "security": "WPA2"}])
    assert 'id="home-url">http://kitchen.local:8080<' in page
    assert "{home_url}" not in page and "{content}" not in page  # nothing left unfilled


def test_a_hostname_cannot_break_out_of_the_address_on_the_page(monkeypatch):
    monkeypatch.setattr(wifi_manager.socket, "gethostname", lambda: 'a"><script>alert(1)</script>')
    page = wifi_manager.render_network_list_html([])
    assert "<script>alert(1)" not in page


def test_stopping_the_hotspot_also_frees_port_80(monkeypatch):
    stopped = []
    monkeypatch.setattr(wifi_manager.captive_responder, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(wifi_manager.subprocess, "run", lambda cmd, **kw: completed())
    WiFiManager.stop_ap()
    assert stopped == [True]
