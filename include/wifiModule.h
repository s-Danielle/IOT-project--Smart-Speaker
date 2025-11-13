
#include <Arduino.h>
#include <WiFi.h>

#pragma once

namespace WifiModule {

namespace {
constexpr uint32_t kRetryDelayMs = 250;

const char *statusToString(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS:
      return "WL_IDLE_STATUS";
    case WL_NO_SSID_AVAIL:
      return "WL_NO_SSID_AVAIL";
    case WL_SCAN_COMPLETED:
      return "WL_SCAN_COMPLETED";
    case WL_CONNECTED:
      return "WL_CONNECTED";
    case WL_CONNECT_FAILED:
      return "WL_CONNECT_FAILED";
    case WL_CONNECTION_LOST:
      return "WL_CONNECTION_LOST";
    case WL_DISCONNECTED:
      return "WL_DISCONNECTED";
#ifdef WL_WRONG_PASSWORD
    case WL_WRONG_PASSWORD:
      return "WL_WRONG_PASSWORD";
#endif
    default:
      return "UNKNOWN";
  }
}
}  // namespace

bool connect(const char *ssid, const char *password, uint32_t timeoutMs) {
  if (!ssid || !password) {
    Serial.println("[WifiModule] SSID or password pointer is null.");
    return false;
  }

  if (WiFi.status() == WL_CONNECTED) {
    // Already connected; nothing to do.
    return true;
  }

  if (WiFi.status() == WL_NO_SHIELD) {
    Serial.println("we got no shield whatever that means");
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  Serial.printf("[WifiModule] Connecting to SSID: %s\n", ssid);
  WiFi.begin(ssid, password);

  const uint32_t start = millis();
  wl_status_t lastStatus = WL_IDLE_STATUS;
  while (WiFi.status() != WL_CONNECTED &&
         (millis() - start) < timeoutMs) {
    const wl_status_t status = WiFi.status();
    if (status != lastStatus) {
      Serial.printf("[WifiModule] Status: %s (%d)\n", statusToString(status),
                    static_cast<int>(status));
      lastStatus = status;
      if (status == WL_CONNECT_FAILED) {
        break;
      }
#ifdef WL_WRONG_PASSWORD
      if (status == WL_WRONG_PASSWORD) {
        break;
      }
#endif
    }
    delay(kRetryDelayMs);
  }

  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected) {
    Serial.println("\n[WifiModule] Connected successfully.");
    Serial.printf("[WifiModule] IP address: %s\n",
                  WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WifiModule] Connection timed out.");
    Serial.printf("[WifiModule] Final status: %s (%d)\n",
                  statusToString(WiFi.status()),
                  static_cast<int>(WiFi.status()));
    WiFi.disconnect(true, true);
  }

  return connected;
}

bool isConnected() {
  return WiFi.status() == WL_CONNECTED;
}

IPAddress localIP() {
  return WiFi.localIP();
}

void disconnect(bool wifioff) {
  WiFi.disconnect(true, true);
  if (wifioff) {
    WiFi.mode(WIFI_OFF);
  }
}

}  // namespace WifiModule


