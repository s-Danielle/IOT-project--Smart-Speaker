// Web / unsupported-platform stub for wifi_iot.
// wifi_setup_screen.dart uses a conditional import so this file is compiled
// on web and the real wifi_connector.dart is compiled on Android.
// All methods are no-ops that signal failure so the wizard falls through
// to the guided-instructions path.
abstract class WifiConnector {
  static Future<bool> connectToSetupAp(String ssid) async => false;
  static Future<void> releaseWifiBinding() async {}
}
