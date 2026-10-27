# Manual Test Checklist — WiFi Provisioning & Web App

End-to-end test procedures for the WiFi provisioning flow and the Pi-served
Flutter web app. Run these on real hardware (Raspberry Pi + phone + laptop).

## Reference

**LED expectations (Light 1, driven by the WiFi provisioner):**

| State | LED |
|-------|-----|
| Waiting for auto-connect (one minute) | Yellow pulsing |
| AP mode active (`SmartSpeaker-Setup`) | Blue pulsing |
| Connected to WiFi | Green solid |
| Connection failure feedback | Red triple flash |

After provisioning completes, the health monitor takes over Light 1
(green solid = all OK).

**Log files for debugging:**

- WiFi provisioner: `/var/log/smart_speaker_wifi.log`
- API server (portal, WiFi API, web app): `/var/log/smart_speaker_server.log`
- Health monitor: `/var/log/smart_speaker_health.log`
- Live systemd view: `journalctl -u smart_speaker_wifi -u smart_speaker_server -f`

**Key facts:** AP SSID `SmartSpeaker-Setup`, AP IP `192.168.4.1`, all HTTP on
port **8080** (plus a port-80 captive responder while the AP is up). Portal
URL: `http://192.168.4.1:8080/wifi-setup`. Connect attempts are async — poll
`GET /debug/wifi/connect-status` (states: `idle` / `connecting` /
`connected` / `failed`).

---

## 1. Fresh-boot provisioning (happy path)

Setup: remove all saved WiFi profiles on the Pi
(`sudo nmcli connection delete <name>` for each WiFi profile), then reboot.

- [ ] Within about 1.5 minutes of boot (the speaker waits one minute for a network first), `SmartSpeaker-Setup` appears in the phone's WiFi list
- [ ] Light 1: yellow pulsing during the wait, then blue pulsing once the AP is up
- [ ] Join `SmartSpeaker-Setup` from the phone
- [ ] Captive-portal popup ("Sign in to network") opens automatically and shows the setup page with a network list
- [ ] If no popup: browsing to any http:// site redirects to the portal; `http://192.168.4.1:8080/wifi-setup` works directly
- [ ] Pick the home network, enter the password, submit
- [ ] Portal shows a "connecting…" progress page that updates on its own
- [ ] The setup network disappears from the phone, and within a few seconds the page says to bring the phone back to its normal WiFi. The page shows a button "My phone is back on WiFi – open the speaker" and the speaker's address
- [ ] Press the button **before** the phone is back on the home WiFi: the page stays, and says the speaker does not answer yet
- [ ] Bring the phone back to the home WiFi (most phones do it by themselves) and press the button: the web app opens
- [ ] If the phone's "sign in to network" window closed by itself when the setup network went away, open `http://rpi2.local:8080` in the browser: the same result
- [ ] Light 1 turns green solid
- [ ] From a device on the LAN: `http://rpi2.local:8080` loads the web app and `/health` returns OK
- [ ] **No reboot happened** at any point (check `uptime`)

## 2. Wrong-password path

Starting from AP mode (step 1 setup, or force via `POST /debug/wifi/ap-mode`):

- [ ] In the portal, pick a network and enter a **wrong** password
- [ ] The page first asks you to bring the phone back to its WiFi, as in test 1 (it cannot know yet)
- [ ] When the phone rejoins `SmartSpeaker-Setup` (it comes back in the WiFi list, Light 1 blue pulsing), the page by itself changes to a failure message with a "Try Again" button
- [ ] Retry with the **correct** password from the restored portal — succeeds as in test 1

## 3. App WiFi Setup wizard

With the speaker in AP mode and the Flutter app installed on a phone:

- [ ] Open the app's WiFi Setup wizard; it detects/guides you to the speaker's AP
- [ ] On Android: wizard joins `SmartSpeaker-Setup` programmatically; on other platforms it guides you to join manually via WiFi settings
- [ ] Wizard reaches the speaker (via `192.168.4.1:8080`) and shows scanned networks
- [ ] Pick a network, enter password, connect
- [ ] Wizard shows progress (polling connect-status), then "Speaker is switching networks" with a button "My phone is back on WiFi"
- [ ] Pressing the button before the phone is back on its WiFi shows a message that the speaker does not answer yet; once the phone is back, the button (or the automatic check) leads to "Speaker connected!"
- [ ] App then reaches the speaker on the LAN address

## 4. Web app served by the Pi

From a dev machine with Flutter installed:

- [ ] `./scripts/dev/deploy_web.sh` builds and rsyncs to the Pi (default target `iot-proj@rpi2.local`) with no service restart
- [ ] From a laptop browser on the same LAN, open `http://rpi2.local:8080`
- [ ] App loads; chips list, library, and settings/parental controls all read and save correctly
- [ ] NFC chip scanning UI is **absent** on web (hidden on this platform)
- [ ] REST endpoints still respond normally (e.g. `/health`, `/chips`) — the web app does not shadow the API

## 5. AP password variant

- [ ] Set `AP_PASSWORD="<8+ chars>"` in the repo-root `SECRETS` file
- [ ] Delete any existing hotspot profile so it's recreated: `sudo nmcli connection delete SmartSpeaker-Setup`
- [ ] Trigger AP mode (test 1 setup or `POST /debug/wifi/ap-mode`)
- [ ] Phone prompts for the WPA2 password when joining `SmartSpeaker-Setup`; joining with it works and the portal opens as usual
- [ ] Variant: a password **shorter than 8 chars** logs a warning and falls back to an open AP (check `/var/log/smart_speaker_server.log` or the wifi log)
- [ ] Cleanup: clear `AP_PASSWORD` and delete the hotspot profile again if you want an open AP afterwards

## 6. The router comes back after the speaker (a power cut at home)

This is what happens after a power cut: the speaker boots faster than the router, finds no network, and opens its setup hotspot. The speaker must not wait there for ever. While nobody is connected to the hotspot, it tries the saved network again every 2 minutes (`AP_RETRY_INTERVAL` in `Main/wifi_provisioner.py`). If somebody is connected to the hotspot, it leaves them alone.

Setup: switch off the WiFi network the speaker has saved (or take its router out of range), then reboot the Pi.

- [ ] Within about 1.5 minutes of boot, `SmartSpeaker-Setup` appears and Light 1 pulses blue
- [ ] **Do not join the hotspot.** Switch the home network back on
- [ ] Within about 2.5 minutes the hotspot disappears by itself and Light 1 turns green
- [ ] The speaker is reachable on the home network again (`http://rpi2.local:8080`), and **no reboot happened** (check `uptime`)
- [ ] `/var/log/smart_speaker_wifi.log` says it tried the saved network again
- [ ] Variant: switch the home network off again, reboot, and this time **join the hotspot** from a phone and stay connected. Switch the home network on. The speaker must **not** drop the hotspot under you; it keeps waiting for you to finish the setup

## 7. The network goes away while the speaker is running

The speaker does not only check the network at boot. If it has had no network for a minute (the router was replaced, switched off for good, or the speaker was carried to another house), it opens the setup hotspot by itself, and the same steps as in test 1 get it onto the new network. A break shorter than a minute is left alone: the speaker just rejoins.

Setup: the speaker is on and working (Light 1 green, music can play).

- [ ] Switch the home router off for about 20 seconds and on again. `SmartSpeaker-Setup` **does not** appear, and the speaker is back on the home network by itself
- [ ] Switch the home router off and leave it off. After about a minute `SmartSpeaker-Setup` appears and Light 1 pulses blue. **No reboot happened** (check `uptime`)
- [ ] Join `SmartSpeaker-Setup` from the phone and set up a **different** WiFi network (as in test 1, including the button at the end). The speaker joins it, Light 1 turns green, `http://rpi2.local:8080` opens the web app
- [ ] Then switch that new network off and leave it off: after about a minute the hotspot appears again (the speaker keeps watching after the first setup, not only after a boot)
- [ ] `/var/log/smart_speaker_wifi.log` shows `No network. Setup mode starts in 60s unless it comes back` and then `No network for 60s, starting AP mode...`
- [ ] Variant: while the speaker is on the home network, use the app's developer tools to join another network. While it is joining, the hotspot does **not** start
- [ ] The hotspot's port-80 helper is gone after the setup: on the new network `curl -sI http://<speaker address>/` fails to connect instead of redirecting to `192.168.4.1`
