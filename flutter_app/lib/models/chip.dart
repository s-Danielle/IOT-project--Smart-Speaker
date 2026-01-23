class SpeakerChip {
  final String id;
  final String? uid;
  final String name;
  final String? songId;
  final String? songName;

  SpeakerChip({
    required this.id,
    this.uid,
    required this.name,
    this.songId,
    this.songName,
  });

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
