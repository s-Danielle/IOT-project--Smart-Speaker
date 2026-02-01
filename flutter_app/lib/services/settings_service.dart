// =============================================================================
// SETTINGS SERVICE
// =============================================================================
//
// Persists app preferences on the device using [SharedPreferences] (key-value
// store, backed by platform storage). Used mainly for the speaker base URL so
// the app knows which backend to call (e.g. http://smart-speaker-iot.local:8080).
//
// All methods are static and async; call with await from async code.
//
// =============================================================================

import 'package:shared_preferences/shared_preferences.dart';

/// Persistent app settings (currently: speaker base URL).
class SettingsService {
  /// Key under which the base URL is stored in SharedPreferences.
  static const _baseUrlKey = 'speaker_base_url';

  /// Default base URL used when none is set (e.g. first launch or after reset).
  static const defaultBaseUrl = 'http://smart-speaker-iot.local:8080';

  /// Returns the stored speaker base URL, or [defaultBaseUrl] if not set.
  /// Used by screens before creating [ApiService](baseUrl).
  static Future<String> getBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_baseUrlKey) ?? defaultBaseUrl;
  }

  /// Saves the speaker base URL (e.g. after user edits it in Settings screen).
  static Future<void> setBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_baseUrlKey, url);
  }

  /// Removes the stored base URL so [getBaseUrl] will return [defaultBaseUrl].
  static Future<void> resetToDefault() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_baseUrlKey);
  }
}
