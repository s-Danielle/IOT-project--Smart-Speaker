import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:shared_preferences/shared_preferences.dart';

class SettingsService {
  static const _baseUrlKey = 'speaker_base_url';

  /// On web the app is served by the speaker itself, so the page's own
  /// origin is the API base URL and no configuration is needed.
  /// On mobile we rely on mDNS resolution of the speaker's hostname.
  static String get defaultBaseUrl =>
      kIsWeb ? Uri.base.origin : 'http://rpi2.local:8080';

  static Future<String> getBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_baseUrlKey) ?? defaultBaseUrl;
  }

  static Future<void> setBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_baseUrlKey, url);
  }

  static Future<void> resetToDefault() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_baseUrlKey);
  }
}
