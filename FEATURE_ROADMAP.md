# Smart Speaker - Feature Roadmap

## Features Overview

| # | Feature | Status |
|---|---------|--------|
| 1 | WebSocket Real-Time | TODO |
| 2 | PTT Voice Commands | TODO |
| 3 | Parental Controls | DONE ✅ |
| 4 | Usage Analytics | TODO |
| 5 | Fix README | TODO |
| 6 | Service Separation | DONE ✅ |
| 7 | WiFi Provisioning | TODO |
| 8 | LED Feedback | TODO |

---

## Current Status: ✅ A-

**Working:** REST API, Flutter App, NFC, Buttons, Volume Control, Auto Chip Registration, Parental Controls, Developer Tools, Service Separation

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

## 2. 🎙️ PTT Voice Commands (3-4 hrs)

**What:** Press dedicated button, speak command → action executes  
**Trigger:** Dedicated PTT button (future hardware addition)

**Flow:**
1. Press PTT button → LED turns blue (listening)
2. Speaker plays "beep" 
3. Listen for 2-3 seconds (fixed duration)
4. LED pulses cyan (processing)
5. Execute command → LED flashes green/red (success/fail)
6. Speaker confirms: "Playing jazz" or "Not recognized"

**Commands to support:**
- "Play [song name]" → search library and play
- "Pause" / "Stop" / "Next"
- "Volume up" / "Volume down"

**Hardware (future):**
- Dedicated PTT button (new GPIO or I2C expander)
- Optional: Dedicated LED (Light 3) for voice mode feedback
- Could share existing Light 2 if no dedicated LED available

**Implementation:**
- Use Vosk (offline speech-to-text, ~50MB model)
- Add `BUTTON_PTT_BIT` to settings.py when hardware added
- Integrate with LED system (Light 3 or shared Light 2)

**Dependencies:** `vosk`, `sounddevice`

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

**What:** Auto-create hotspot when no WiFi available for easy setup

**Flow:**
```
Boot → Check WiFi → Connected? 
  ├─ Yes → Normal startup
  └─ No → Create "SmartSpeaker-Setup" AP
          → Captive portal for WiFi config
          → Connect to selected network
```

**Implementation:** Use `comitup` package (Raspberry Pi WiFi provisioning)

**See:** `FIXES_AND_IMPROVEMENTS.md` for detailed implementation

---

## 8. 💡 LED Feedback System (2-3 hrs)

**What:** Visual feedback through 2 dedicated RGB LEDs (PCF8574 @ 0x21)

**LED Assignment:**
| LED | Purpose | Examples |
|-----|---------|----------|
| Light 1 | Device Health | WiFi status, service errors, booting |
| Light 2 | Player State | Playing, paused, recording, blocked |
| Light 3 (future) | PTT Voice Mode | Listening, processing, result |

**Extensible design** for adding PTT button + LED later.

**See:** `FIXES_AND_IMPROVEMENTS.md` for full pattern tables and code

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
