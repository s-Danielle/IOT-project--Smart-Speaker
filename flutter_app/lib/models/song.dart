// =============================================================================
// SONG MODEL
// =============================================================================
//
// Represents one entry in the speaker's music library. Songs can be added via
// the app (name + URI, or file upload). Chips are then assigned to a song so
// that tapping the chip plays this song on the device.
//
// =============================================================================

/// One song in the library: backend ID, display name, and playable URI.
///
/// [uri] is typically a Spotify URI (spotify:track:...) or a local/file URI
/// returned by the backend after uploading a file.
class Song {
  /// Backend-assigned song ID (used in API paths like PUT /library/{id}).
  final String id;

  /// Display name shown in the app (e.g. "Morning playlist").
  final String name;

  /// Playable URI (Spotify URI or device-specific URI after file upload).
  final String uri;

  Song({
    required this.id,
    required this.name,
    required this.uri,
  });

  /// Builds a [Song] from the JSON map returned by the API.
  /// [json] keys: "id", "name", "uri".
  factory Song.fromJson(Map<String, dynamic> json) {
    return Song(
      id: json['id'],
      name: json['name'] ?? '',
      uri: json['uri'] ?? '',
    );
  }

  /// Serializes this song to JSON (e.g. for PUT body). Omits [id] as it is set by the server.
  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'uri': uri,
    };
  }
}
