# Smart Speaker - Feature Roadmap

## Features Overview

| # | Feature | Status |
|---|---------|--------|
| 1 | WebSocket Real-Time | TODO |
| 2 | PTT Voice Commands | TODO |
| 3 | Parental Controls | DONE |
| 4 | Usage Analytics | TODO |
| 5 | Fix README | TODO |
| 6 | Service Separation | DONE |

---

## Current Status: ✅ B+/A-

Working: REST API, Flutter App, NFC, Buttons, Volume Control, Auto Chip Registration

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
**Trigger:** Button 6 on IO expander (P5) - dedicated PTT button

**Flow:**
1. Press PTT button
2. Speaker plays "beep" (listening)
3. Listen for 2-3 seconds (fixed duration)
4. Auto-process speech → execute command
5. Speaker confirms: "Playing jazz" or "Not recognized"

**Commands to support:**
- "Play [song name]" → search library and play
- "Pause" / "Stop" / "Next"
- "Volume up" / "Volume down"

**Implementation:**
- Use Vosk (offline speech-to-text, ~50MB model)
- Add `BUTTON_PTT_BIT = 5` to settings.py

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

## Priority Order

| # | Feature | Time | Demo Value |
|---|---------|------|------------|
| 1 | WebSocket | 3-4 hrs | ⭐⭐⭐⭐ |
| 2 | PTT Voice | 3-4 hrs | ⭐⭐⭐⭐⭐ |
| 3 | Parental Controls | DONE | ⭐⭐⭐⭐ |
| 4 | Analytics | 2-3 hrs | ⭐⭐⭐ |
| 5 | README | 15 min | ⭐⭐ |
| 6 | Service Separation | DONE | ⭐⭐⭐⭐ |
