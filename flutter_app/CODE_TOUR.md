# Flutter App – Code Tour

This document explains how the Smart Speaker companion app is structured so you can follow the code and understand what each part does.

## Entry point

- **`lib/main.dart`** – App entry: `main()` → `runApp(MyApp)`. `MyApp` is a `StatelessWidget` that builds a `MaterialApp` with theme and `home: HomeScreen()`. All other screens are opened by pushing routes on top of this.

## Project layout

```
lib/
  main.dart              # Entry + root MaterialApp
  screens/               # Full-screen UIs
  models/                # Data classes (API ↔ UI)
  services/              # API client, storage, Spotify helpers
```

## Models (`lib/models/`)

Plain Dart classes used to represent data from the API (and sometimes sent back).

- **`status.dart`** – `Status`: `connected`, `chipId`. From GET /status.
- **`chip.dart`** – `SpeakerChip`: `id`, `uid`, `name`, `songId`, `songName`. From GET/POST/PUT /chips.
- **`song.dart`** – `Song`: `id`, `name`, `uri`. From GET/POST/PUT/DELETE /library.
- **`parental_settings.dart`** – `QuietHours` (enabled, start, end) and `ParentalSettings` (enabled, volumeLimit, quietHours, dailyLimitMinutes, chipBlacklist, chipWhitelistMode, chipWhitelist). From GET/PUT /settings/parental.

All models have `fromJson` (and some have `toJson` / `copyWith`) for API serialization.

## Services (`lib/services/`)

- **`api_service.dart`** – HTTP client for the Smart Speaker backend. `ApiService(baseUrl)`; methods like `getStatus()`, `getChips()`, `createChip()`, `getLibrary()`, `createSong()`, `uploadFile()`, parental, debug, WiFi. All async; throw on non-2xx.
- **`settings_service.dart`** – Persists app settings (currently only speaker base URL) via `SharedPreferences`. Static methods: `getBaseUrl()`, `setBaseUrl()`, `resetToDefault()`.
- **`spotify_utils.dart`** – `convertSpotifyUrlToUri()`, `isSpotifyUrl()`, `isSpotifyUri()`. Used when adding/editing library entries with Spotify links.

## Screens (`lib/screens/`)

Each screen is a `StatefulWidget` with a private `State` class that holds mutable state (`_status`, `_loading`, `_error`, etc.), calls the API in `initState()` or on button press, and uses `setState()` to refresh the UI.

- **`home_screen.dart`** – First screen. Shows connection status (GET /status), “Scan Chip” button, and nav cards to Chips, Library, Settings. Refresh on init and from app bar; also refresh after returning from Settings.
- **`scan_chip_screen.dart`** – NFC scan: start session, read tag UID, stop session, then `_syncChip(uid)` to match GET /chips. New chip → “Setup Chip” (POST /chips). Existing → Rename, Assign Song, Reset. Uses `nfc_manager` (Android: `NfcTagAndroid.id`).
- **`chips_screen.dart`** – List of chips (GET /chips) and library (GET /library). Per chip: PopupMenu with Rename, Assign Song, Reset Assignment, Delete. Dialogs for input; API calls then `_loadData()`.
- **`library_screen.dart`** – List of songs (GET /library). Add manually (name + Spotify URL/URI) or from file (pick file → POST /files → create song). Edit/Delete via popup. Uses `convertSpotifyUrlToUri` when adding/editing. FAB: small “upload file”, main “add”.
- **`settings_screen.dart`** – Speaker base URL (load/save via SettingsService), “Test Connection” (GET /status), advanced section (custom URL, Reset, Save), entries to Parental Controls and Developer Tools.
- **`parental_controls_screen.dart`** – Load GET /settings/parental and GET /chips. Edit enable, volume limit, quiet hours (time pickers), daily limit, chip whitelist/blacklist. Save via PUT /settings/parental.
- **`developer_tools_screen.dart`** – System info, I2C devices, git status, speaker start/stop/restart, daemon reload, run main, WiFi status/scan/connect/forget/AP mode, logs, reboot Pi. All via ApiService debug endpoints.

## Patterns used in the app

1. **StatefulWidget + setState** – Screen state holds data and loading/error flags; `initState()` or a button starts an async load; after `await`, `setState()` updates the fields and triggers a rebuild.
2. **Async/await** – All API calls are `async`; the UI uses `await` and then `setState()`. After any `await`, use `if (mounted)` before using `context` (e.g. SnackBar) so you don’t use a disposed widget.
3. **Navigation** – `Navigator.push(context, MaterialPageRoute(builder: (_) => SomeScreen()))`. Back pops the route. You can `await Navigator.push(...)` and then run code when the user returns (e.g. refresh).
4. **Dialogs** – `showDialog(context: context, builder: (context) => AlertDialog(...))`. Close with `Navigator.pop(context)` or `Navigator.pop(context, result)` to return a value to the caller.
5. **Theme** – `Theme.of(context)` and `theme.colorScheme` / `theme.textTheme` for consistent colors and text styles set in `main.dart`.

## Reading order (for learning)

1. `main.dart` – entry and theme.
2. `models/status.dart`, `models/chip.dart` – simple data + `fromJson`.
3. `services/api_service.dart` – first few methods (e.g. `getStatus`, `getChips`) to see `Future` and JSON.
4. `screens/home_screen.dart` – full flow: state, `initState`, `_refresh`, `setState`, `build`, navigation.
5. `screens/chips_screen.dart` – lists, dialogs, `mounted`, more API usage.
6. `screens/scan_chip_screen.dart` – NFC flow and chip registration.
7. Other screens and the rest of `api_service.dart` as needed.

The source files themselves contain file-level and class/method-level comments that describe each part in more detail.
