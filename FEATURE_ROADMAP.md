# Smart Speaker - Feature Roadmap

## Features Overview

| # | Feature | Status |
|---|---------|--------|
| 1 | WebSocket Real-Time | TODO |
| 2 | PTT Voice Commands | DONE ✅ |
| 3 | Parental Controls | DONE ✅ |
| 4 | Usage Analytics | TODO |
| 5 | Fix README | TODO |
| 6 | Service Separation | DONE ✅ |
| 7 | WiFi Provisioning | TODO |
| 8 | LED Feedback | TODO |

---

## Current Status: ✅ A-

**Working:** REST API, Flutter App, NFC, Buttons, Volume Control, Auto Chip Registration, Parental Controls, Developer Tools, Service Separation, PTT Voice Commands

**Recent Additions (Jan 2026):**
- Parental controls with volume limits, quiet hours, chip whitelists
- Developer tools screen with service management, logs, git operations
- Separated server and hardware controller as independent services
- Debug logging to files for remote troubleshooting

---

## 1. 🔄 WebSocket Real-Time Updates (3-4 hrs)

**Problem:** App needs manual refresh to see changes  
**Solution:** Server pushes updates instantly via WebSocket

**Events to broadcast:**
- `chip_loaded`, `playback_started/paused/stopped`, `volume_changed`, `recording_saved`

**Implementation:**
- Server: Add `websockets` library, broadcast from actions
- Flutter: Add `web_socket_channel`, listen for events

---

## 2. 🎙️ PTT Voice Commands - DONE ✅

**What:** Press dedicated button, speak command → action executes  
**Trigger:** Dedicated PTT button on P5 (I2C expander at 0x20)

**Flow:**
1. Press PTT button → LED turns blue (listening)
2. Listen for 2.5 seconds (fixed duration)
3. LED turns cyan (processing via Google Speech API)
4. Execute command → LED flashes green/red (success/fail)
5. Health monitor restores LED within 5 seconds

**Supported Commands:**
- "hi speaker play" → play/resume
- "hi speaker pause" → pause
- "hi speaker stop" → stop
- "hi speaker clear" → clear chip assignment

**Hardware:**
- PTT button on P5 of button I2C expander (0x20)
- Uses Light 1 (health LED) for feedback during PTT

**Implementation:**
- Uses Google Speech API via SpeechRecognition library (requires internet)
- Works on Pi Zero (ARMv6) - Vosk not supported on this architecture
- `BUTTON_PTT_BIT = 5` in settings.py

**Dependencies:** `SpeechRecognition`, `flac` (system package)

**Setup:** Run `scripts/install-ptt-deps.sh`

---

## 3. 👨‍👩‍👧 Parental Controls - DONE ✅

**Implemented Features:**
- Volume limit (cap at configurable %)
- Quiet hours (disable playback during set times)
- Chip whitelist/blacklist
- Daily usage time limit

**Implementation:**
- Settings stored in `server_data.json`
- Flutter `ParentalControlsScreen` to configure limits
- Controller enforces limits before playback actions
- Blocked actions logged and show feedback

---

## 4. 📊 Usage Analytics (2-3 hrs)

**What:** Track plays, recordings, most-used chips  
**How:** 
- Log events to `analytics.json`
- Add `GET /analytics/summary` endpoint
- Show stats in Flutter app

---

## 5. 📝 Fix README (15 min)

Replace PillTrack content with Smart Speaker docs.

---

## 6. 🔧 Service Separation - DONE ✅

**What:** Split server and hardware controller into separate systemd services

**Architecture:**
- `smart_speaker_server.service` - API server (always running)
- `smart_speaker.service` - Hardware controller (can restart without losing API)

**Benefits:**
- App stays connected when restarting speaker hardware
- Server is single source of truth for all data
- Clean separation of concerns

**Files:**
- `Main/server_main.py` - Standalone server entry point
- `Main/utils/server_client.py` - HTTP client for controller
- `services/smart_speaker_server.service` - Server systemd unit
- Updated `services/smart_speaker.service` - Hardware controller unit

---

## 7. 📶 WiFi Provisioning (2-3 hrs)

**What:** Manage WiFi connections via NetworkManager with AP fallback + app control

**Problem:** 
- Headless device needs keyboard/SSH to configure WiFi
- No way to manage saved networks from the app
- No way to test AP mode without losing connections

**Solution:** NetworkManager-based system with full API control

**Flow:**
```
Boot → NetworkManager auto-connects to known networks
  ├─ Connected → Green LED, normal operation
  └─ No known networks → Wait 30s → Start AP mode
                         → Blue pulsing LED
                         → Captive portal at 192.168.4.1
                         → User configures WiFi
                         → Reboot into normal mode
```

**API Endpoints (for Flutter app):**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/debug/wifi/status` | GET | Current connection (ssid, ip, signal) |
| `/debug/wifi/connections` | GET | List saved networks |
| `/debug/wifi/scan` | GET | Scan available networks |
| `/debug/wifi/connect` | POST | Connect to network |
| `/debug/wifi/forget` | POST | Delete saved network |
| `/debug/wifi/priority` | POST | Set network priority |
| `/debug/wifi/ap-mode` | POST | **Force AP mode for testing** |

**Components:**
- `Main/wifi_provisioner.py` - Boot-time provisioner (NetworkManager-based)
- `services/smart_speaker_wifi.service` - Systemd unit
- Server endpoints for app control

**LED Integration (Light 1):**
| State | Color | Pattern |
|-------|-------|---------|
| Waiting for auto-connect | Yellow | Pulsing |
| AP Mode (setup) | Blue | Pulsing |
| Connected | Green | Solid |
| Connection failed | Red | Triple flash |

**Key Features:**
- ✅ Keeps existing nmtui-configured networks
- ✅ Auto-connects to best available known network
- ✅ Manage networks from Flutter app
- ✅ Force AP mode for testing without losing configs
- ✅ Priority-based network selection

**See:** `FIXES_AND_IMPROVEMENTS.md` Section 4 for full implementation

---

## 8. 💡 LED Feedback System (2-3 hrs)

**What:** Visual feedback through 2 dedicated RGB LEDs (PCF8574 @ 0x21)

**Architecture:**
| LED | Purpose | Controller | Key Colors |
|-----|---------|------------|------------|
| Light 1 | Device Health | `health_monitor.py` (separate service) | Green=OK, Yellow=partial, Red=error |
| Light 2 | Player State | `Main` via `ui/lights.py` | Green=playing, Yellow=paused, Red=recording |
| Light 3 | PTT Voice (future) | TBD | Blue=listening, Cyan=processing |

**Main ignores Light 1** - health is monitored by a separate service that checks:
- Internet connectivity (ping 8.8.8.8)
- Server status (GET /health)
- Hardware status (GET /debug/speaker/status)

**See:** `FIXES_AND_IMPROVEMENTS.md` for full pattern tables and implementation code

---

## Priority Order

| # | Feature | Time | Demo Value |
|---|---------|------|------------|
| 1 | LED Feedback | 2-3 hrs | ⭐⭐⭐⭐⭐ |
| 2 | WiFi Provisioning | 2-3 hrs | ⭐⭐⭐⭐⭐ |
| 3 | WebSocket | 3-4 hrs | ⭐⭐⭐⭐ |
| 4 | PTT Voice | 3-4 hrs | ⭐⭐⭐⭐⭐ |
| 5 | Parental Controls | DONE | ⭐⭐⭐⭐ |
| 6 | Analytics | 2-3 hrs | ⭐⭐⭐ |
| 7 | README | 15 min | ⭐⭐ |
| 8 | Service Separation | DONE | ⭐⭐⭐⭐ |
