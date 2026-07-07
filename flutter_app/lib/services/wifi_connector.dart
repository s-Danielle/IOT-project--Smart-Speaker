import 'package:permission_handler/permission_handler.dart';
import 'package:wifi_iot/wifi_iot.dart';

/// Android implementation of hotspot join for the WiFi setup wizard.
/// Loaded only on native (dart.library.io) via conditional import.
abstract class WifiConnector {
  /// Programmatically join an open WiFi AP and route this app's traffic
  /// through it. Returns true if connected and traffic is bound.
  static Future<bool> connectToSetupAp(String ssid) async {
    // Android >= 10 requires location permission to connect to WiFi.
    final status = await Permission.locationWhenInUse.request();
    if (!status.isGranted) return false;

    try {
      final connected = await WiFiForIoTPlugin.connect(
        ssid,
        security: NetworkSecurity.NONE,
        joinOnce: true,
        withInternet: false,
        timeoutInSeconds: 20,
      );
      if (connected) {
        // Route this app's HTTP traffic over the AP network, not cellular.
        await WiFiForIoTPlugin.forceWifiUsage(true);
      }
      return connected;
    } catch (_) {
      return false;
    }
  }

  /// Undo forceWifiUsage and disconnect from the AP.
  /// Call after provisioning is complete (success or cancel).
  static Future<void> releaseWifiBinding() async {
    try {
      await WiFiForIoTPlugin.forceWifiUsage(false);
    } catch (_) {}
    try {
      await WiFiForIoTPlugin.disconnect();
    } catch (_) {}
  }
}
