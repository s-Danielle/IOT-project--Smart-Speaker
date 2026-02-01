// =============================================================================
// SPEAKER CHIP MODEL
// =============================================================================
//
// Represents one NFC chip registered with the Smart Speaker. Each chip can be
// given a friendly name and optionally assigned to a song in the library.
// The backend stores chips; this model mirrors the API response (GET /chips,
// POST /chips, etc.).
//
// =============================================================================

/// One registered NFC chip: ID, optional UID, name, and optional song assignment.
///
/// [id] is the backend's stable ID. [uid] is the raw NFC UID (may be null for
/// older records). [songId] / [songName] are set when the chip is assigned to
/// a library song.
class SpeakerChip {
  /// Backend-assigned chip ID (used in API paths like PUT /chips/{id}).
  final String id;

  /// Raw NFC tag UID, if available (e.g. from registration).
  final String? uid;

  /// User-facing label for this chip (e.g. "Kids morning").
  final String name;

  /// ID of the assigned song in the library, or null if not assigned.
  final String? songId;

  /// Cached name of the assigned song; may be null even when [songId] is set.
  final String? songName;

  SpeakerChip({
    required this.id,
    this.uid,
    required this.name,
    this.songId,
    this.songName,
  });

  /// Builds a [SpeakerChip] from the JSON map returned by the API.
  /// [json] keys: "id", "uid", "name", "song_id", "song_name" (snake_case from API).
  factory SpeakerChip.fromJson(Map<String, dynamic> json) {
    return SpeakerChip(
      id: json['id'],
      uid: json['uid'],
      name: json['name'] ?? '',
      songId: json['song_id'],
      songName: json['song_name'],
    );
  }
}
