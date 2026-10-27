"""The "connecting..." page of the WiFi setup: what the person holding the phone sees and can press.

The page's script is run for real under node, against a small stand-in for the browser (a page tree,
timers that the test winds forward, and a fetch that answers as the speaker would). Without node the
script-running tests are skipped; the text checks always run.
"""

import json
import shutil
import subprocess

import pytest

NODE = shutil.which("node")

# The stand-in for the browser. It reads one scenario on stdin and prints what the page ended up showing.
HARNESS = r"""
const fs = require('fs');
const scenario = JSON.parse(fs.readFileSync(0, 'utf8'));

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this._text = ''; this.className = ''; this.disabled = false; this.onclick = null; }
  appendChild(c) { this.children.push(c); return c; }
  set innerHTML(v) { this.children = []; this._text = ''; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(' '); }
  find(tag) { return this.children.filter(c => c.tag === tag); }
}
const box = new Node('div'), ssidSpan = new Node('span');
global.document = {
  getElementById: id => (id === 'connect-status' ? box : ssidSpan),
  createElement: tag => new Node(tag),
};
global.window = { AbortController };
global.location = { href: 'http://192.168.4.1:8080/wifi-setup/connect' };

const timers = [];
global.setTimeout = fn => { timers.push(fn); return timers.length; };
global.clearTimeout = () => {};

// What the speaker answers, per call: the status route follows scenario.status, then repeats its last entry
const asked = { status: 0, probes: [] };
global.fetch = (url, opts) => {
  if (url.startsWith('http://')) {  // the speaker on the home network
    asked.probes.push(url);
    return scenario.home_up ? Promise.resolve({}) : Promise.reject(new TypeError('network error'));
  }
  const answer = scenario.status[Math.min(asked.status++, scenario.status.length - 1)];
  if (answer === 'down') return Promise.reject(new TypeError('network error'));
  return Promise.resolve({ json: () => Promise.resolve(answer) });
};

const flush = () => new Promise(r => setImmediate(r));
async function wind(n) {
  for (let i = 0; i < n; i++) { await flush(); const t = timers.shift(); if (!t) break; t(); }
  await flush();
}

(async () => {
  eval(scenario.script);
  await wind(scenario.steps);
  const report = () => ({
    title: (box.find('h2')[0] || {}).textContent,
    text: box.textContent,
    buttons: box.find('button').map(b => ({ label: b.textContent, disabled: b.disabled })),
    notes: box.find('p').filter(p => p.className.includes('note')).map(p => p.textContent),
    box_class: box.className,
    href: location.href,
    probes: asked.probes,
  });
  const before = report();
  let after = null;
  if (scenario.press) {
    const btn = box.find('button')[0];
    btn.onclick();
    await flush(); await flush();
    after = report();
  }
  console.log(JSON.stringify({ before, after }));
})();
"""


def page_script(server_module, ssid="Home WiFi"):
    """The script exactly as the page carries it."""
    html = server_module._render_connecting_html(ssid)
    start = html.index("<script>") + len("<script>")
    return html[start:html.index("</script>", start)]


def run_page(server_module, status, home_up=True, steps=6, press=False, ssid="Home WiFi"):
    scenario = {"script": page_script(server_module, ssid), "status": status, "home_up": home_up,
                "steps": steps, "press": press}
    done = subprocess.run([NODE, "-e", HARNESS], input=json.dumps(scenario), capture_output=True,
                          text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

CONNECTING = {"state": "connecting", "ssid": "Home WiFi"}


# --- the text of the page, no node needed -----------------------------------------------------


def test_the_page_names_the_speaker_by_its_hostname(server_module, monkeypatch):
    monkeypatch.setattr(server_module, "speaker_home_url", lambda: "http://kitchen.local:8080")
    assert '"http://kitchen.local:8080"' in server_module._render_connecting_html("Home")


def test_a_network_name_cannot_break_out_of_the_page(server_module):
    html = server_module._render_connecting_html('</script><script>alert(1)</script>')
    assert html.count("</script>") == 2  # the page's own two (the portal's and this one), not the name's
    assert "<\\/script>" in html  # inside the page's script the name's "</" is written so it cannot close it


def test_the_page_has_no_leftover_markers(server_module):
    html = server_module._render_connecting_html("Home")
    assert "__SSID__" not in html and "__HOME__" not in html and "__AP_NAME__" not in html


# --- the script, run for real ------------------------------------------------------------------


@needs_node
def test_while_the_speaker_still_answers_the_page_just_waits(server_module):
    shown = run_page(server_module, [CONNECTING], steps=6)["before"]
    assert shown["buttons"] == []
    assert shown.get("title") is None  # the "Connecting..." text the page came with is still there, untouched


@needs_node
def test_when_the_setup_network_goes_away_the_page_asks_for_the_phone_to_come_back(server_module):
    shown = run_page(server_module, [CONNECTING, "down"], steps=8)["before"]
    assert [b["label"] for b in shown["buttons"]] == ["My phone is back on WiFi – open the speaker"]
    assert '"Home WiFi"' in shown["text"]
    assert "http://" in shown["text"] and ":8080" in shown["text"]  # the address, to type if the button fails
    assert shown["href"].endswith("/wifi-setup/connect")  # it did not navigate by itself


@needs_node
def test_two_missed_answers_are_not_yet_the_end_of_the_setup_network(server_module):
    shown = run_page(server_module, [CONNECTING, "down", "down", CONNECTING], steps=5)["before"]
    assert shown["buttons"] == []


@needs_node
def test_the_button_opens_the_web_app_when_the_speaker_is_reachable(server_module):
    got = run_page(server_module, ["down"], home_up=True, press=True)
    home = server_module.speaker_home_url()
    assert got["after"]["probes"] == [home + "/health"]  # it looked first
    assert got["after"]["href"] == home + "/"


@needs_node
def test_the_button_stays_on_the_page_when_the_speaker_is_not_reachable_yet(server_module):
    got = run_page(server_module, ["down"], home_up=False, press=True)["after"]
    assert got["href"].endswith("/wifi-setup/connect")  # the phone is not sent to an error page
    assert got["buttons"][0]["disabled"] is False  # and can try again
    assert "does not answer yet" in got["notes"][0]


@needs_node
def test_a_failed_attempt_shows_the_error_and_a_way_to_try_again(server_module):
    failed = {"state": "failed", "ssid": "Home WiFi", "error": "Connection failed (check password and signal)"}
    shown = run_page(server_module, [CONNECTING, failed])["before"]
    assert shown["title"].endswith("Failed")
    assert "check password" in shown["text"]
    assert [b["label"] for b in shown["buttons"]] == ["Try Again"]


@needs_node
def test_if_the_setup_network_comes_back_with_a_failure_the_page_shows_it(server_module):
    # The password was wrong: the speaker puts the hotspot back, the phone rejoins it, and the page
    # that had told the user to go back to their WiFi now says what happened.
    failed = {"state": "failed", "ssid": "Home WiFi", "error": "Connection failed (check password and signal)"}
    shown = run_page(server_module, [CONNECTING, "down", "down", "down", "down", failed], steps=12)["before"]
    assert shown["title"].endswith("Failed")
    assert [b["label"] for b in shown["buttons"]] == ["Try Again"]


@needs_node
def test_a_page_that_hears_connected_offers_the_same_button(server_module):
    shown = run_page(server_module, [{"state": "connected", "ssid": "Home WiFi"}])["before"]
    assert shown["title"].endswith("Connected!")
    assert len(shown["buttons"]) == 1 and "open the speaker" in shown["buttons"][0]["label"]
