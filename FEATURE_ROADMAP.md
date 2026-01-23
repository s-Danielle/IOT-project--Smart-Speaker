# Smart Speaker - Feature Roadmap

## Features Overview

| # | Feature | Status |
|---|---------|--------|
| 1 | WebSocket Real-Time | TODO |
| 2 | PTT Voice Commands | TODO |
| 3 | Parental Controls | TODO |
| 4 | Usage Analytics | TODO |
| 5 | Fix README | TODO |

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

## 3. 👨‍👩‍👧 Parental Controls (2-3 hrs)

**Features:**
- Volume limit (cap at configurable %)
- Quiet hours (disable playback during set times)
- Chip whitelist/blacklist
- Usage time limit per day

**Implementation:**
- Add settings to `server_data.json`
- Flutter screen to configure limits
- Controller checks limits before actions

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

## Priority Order

| # | Feature | Time | Demo Value |
|---|---------|------|------------|
| 1 | WebSocket | 3-4 hrs | ⭐⭐⭐⭐ |
| 2 | PTT Voice | 3-4 hrs | ⭐⭐⭐⭐⭐ |
| 3 | Parental Controls | 2-3 hrs | ⭐⭐⭐⭐ |
| 4 | Analytics | 2-3 hrs | ⭐⭐⭐ |
| 5 | README | 15 min | ⭐⭐ |
