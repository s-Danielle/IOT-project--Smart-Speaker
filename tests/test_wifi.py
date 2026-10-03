"""WiFi setup: a slow start must not leave the speaker in setup mode for ever.

NetworkManager, iwgetid and iw are all replaced by fakes here. Nothing touches the real network.
"""

import subprocess

import pytest

import fakes
import hardware.wifi_manager as wifi_manager
from hardware.wifi_manager import WiFiManager
from wifi_provisioner import AP_RETRY_INTERVAL, CONNECT_TIMEOUT, WiFiProvisioner


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
        self.calls = []

    def is_connected(self):
        return self.connected and not self.ap_up

    def get_current_ssid(self):
        return "Home" if self.connected else ""

    def start_ap(self):
        self.calls.append("start_ap")
        self.ap_up = True
        return True

    def stop_ap(self):
        self.calls.append("stop_ap")
        self.ap_up = False
        return True

    def reconnect(self):
        self.calls.append("reconnect")
        return True

    def has_ap_clients(self):
        return self.clients


def build(limit=3600):
    clock, wifi, led = Clock(limit), FakeWiFi(), fakes.CallLog()
    provisioner = WiFiProvisioner(wifi=wifi, led=led, clock=clock.now, sleep=clock.sleep)
    return provisioner, wifi, clock, led


def test_a_normal_boot_never_starts_the_hotspot():
    provisioner, wifi, clock, led = build()
    wifi.connected = True
    provisioner.run()
    assert wifi.calls == []
    assert "connected" in led.names()


def test_wifi_that_arrives_within_the_wait_never_starts_the_hotspot():
    provisioner, wifi, clock, led = build()
    clock.on_tick = lambda t: setattr(wifi, "connected", t >= 10)
    provisioner.run()
    assert wifi.calls == []


def test_no_wifi_at_boot_starts_the_hotspot():
    provisioner, wifi, clock, led = build(limit=CONNECT_TIMEOUT + 20)
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls == ["start_ap"]
    assert "ap_mode" in led.names()


def test_the_speaker_gets_out_of_setup_mode_when_the_wifi_comes_back():
    # Sep 5: the router was not ready within 30 s, the speaker opened its hotspot, and then
    # sat there with no internet until somebody rebooted it.
    provisioner, wifi, clock, led = build()
    clock.on_tick = lambda t: setattr(wifi, "connected", t >= 100)  # the router comes up at 100 s
    provisioner.run()  # must come back by itself
    assert wifi.calls == ["start_ap", "stop_ap", "reconnect"]
    assert led.names()[-1] == "connected"
    assert clock.t < 30 + AP_RETRY_INTERVAL + CONNECT_TIMEOUT + 10


def test_if_the_wifi_is_still_down_the_hotspot_comes_back():
    provisioner, wifi, clock, led = build(limit=30 + 3 * AP_RETRY_INTERVAL)
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls.count("start_ap") >= 3  # up, down for a retry, up again, ...
    assert wifi.calls.count("stop_ap") >= 2
    assert wifi.ap_up or wifi.calls[-1] in ("stop_ap", "reconnect")  # it is never left dead for long


def test_nobody_is_thrown_off_the_hotspot_while_setting_it_up():
    provisioner, wifi, clock, led = build(limit=30 + 3 * AP_RETRY_INTERVAL)
    wifi.clients = True
    with pytest.raises(TimeoutError):
        provisioner.run()
    assert wifi.calls == ["start_ap"]  # never stopped


def test_setting_up_through_the_portal_still_works():
    provisioner, wifi, clock, led = build()

    def server_connects(t):
        if t >= 60:  # the portal joined a network and tore the hotspot down
            wifi.ap_up = False
            wifi.connected = True

    clock.on_tick = server_connects
    provisioner.run()
    assert "stop_ap" not in wifi.calls  # the provisioner did not need to do anything
    assert led.names()[-1] == "connected"


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
