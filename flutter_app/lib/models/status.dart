// =============================================================================
// STATUS MODEL
// =============================================================================
//
// Represents the current state of the Smart Speaker device as returned by the
// backend API (GET /status). Used on the home screen to show connection status
// and which chip (if any) is currently "active" on the speaker.
//
// =============================================================================

/// Snapshot of the speaker's connection and current chip.
///
/// Returned by [ApiService.getStatus]. All fields are read-only (final).
class Status {
  /// Whether the app/device is successfully talking to the speaker backend.
  final bool connected;

  /// If the speaker has a chip loaded (e.g. scanned on the device), its ID; otherwise null.
  final String? chipId;

  Status({required this.connected, this.chipId});

  /// Builds a [Status] from the JSON map returned by the API.
  /// [json] keys: "connected" (bool), "chip_id" (string or null).
  factory Status.fromJson(Map<String, dynamic> json) {
    return Status(
      connected: json['connected'] ?? false,
      chipId: json['chip_id'],
    );
  }
}
