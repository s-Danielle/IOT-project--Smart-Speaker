# Manual Test Checklist — WiFi Provisioning & Web App

End-to-end test procedures for the WiFi provisioning flow and the Pi-served
Flutter web app. Run these on real hardware (Raspberry Pi + phone + laptop).

## Reference

**LED expectations (Light 1, driven by the WiFi provisioner at boot):**

| State | LED |
|-------|-----|
| Waiting for auto-connect (~30s window) | Yellow pulsing |
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

- [ ] Within ~45s of boot, `SmartSpeaker-Setup` appears in the phone's WiFi list
- [ ] Light 1: yellow pulsing during the wait, then blue pulsing once the AP is up
- [ ] Join `SmartSpeaker-Setup` from the phone
- [ ] Captive-portal popup ("Sign in to network") opens automatically and shows the setup page with a network list
- [ ] If no popup: browsing to any http:// site redirects to the portal; `http://192.168.4.1:8080/wifi-setup` works directly
- [ ] Pick the home network, enter the password, submit
- [ ] Portal shows a "connecting…" progress page that updates on its own
- [ ] Speaker joins the LAN (AP disappears; the progress page eventually reports success or tells you how to reach the speaker on the LAN)
- [ ] Light 1 turns green solid
- [ ] From a device on the LAN: `http://rpi2.local:8080` loads the web app and `/health` returns OK
- [ ] **No reboot happened** at any point (check `uptime`)

## 2. Wrong-password path

Starting from AP mode (step 1 setup, or force via `POST /debug/wifi/ap-mode`):

- [ ] In the portal, pick a network and enter a **wrong** password
- [ ] Progress page eventually shows a failure/error message
- [ ] `SmartSpeaker-Setup` AP comes back up (phone can rejoin; Light 1 blue pulsing)
- [ ] Retry with the **correct** password from the restored portal — succeeds as in test 1

## 3. App WiFi Setup wizard

With the speaker in AP mode and the Flutter app installed on a phone:

- [ ] Open the app's WiFi Setup wizard; it detects/guides you to the speaker's AP
- [ ] On Android: wizard joins `SmartSpeaker-Setup` programmatically; on other platforms it guides you to join manually via WiFi settings
- [ ] Wizard reaches the speaker (via `192.168.4.1:8080`) and shows scanned networks
- [ ] Pick a network, enter password, connect
- [ ] Wizard shows progress (polling connect-status) and confirms success
- [ ] App then reaches the speaker on the LAN address

## 4. Web app served by the Pi

From a dev machine with Flutter installed:

- [ ] `./scripts/deploy_web.sh` builds and rsyncs to the Pi (default target `iot-proj@rpi2.local`) with no service restart
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
