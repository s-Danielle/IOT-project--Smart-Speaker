class SpeakerChip {
  final String id;
  final String name;
  final String? songId;
  final String? songName;

  SpeakerChip({
    required this.id,
    required this.name,
    this.songId,
    this.songName,
  });

  factory SpeakerChip.fromJson(Map<String, dynamic> json) {
    return SpeakerChip(
      id: json['id'],
      name: json['name'] ?? '',
      songId: json['song_id'],
      songName: json['song_name'],
    );
  }
}
