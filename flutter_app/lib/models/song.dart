class Song {
  final String id;
  final String name;
  final String uri;

  Song({
    required this.id,
    required this.name,
    required this.uri,
  });

  factory Song.fromJson(Map<String, dynamic> json) {
    return Song(
      id: json['id'],
      name: json['name'] ?? '',
      uri: json['uri'] ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'uri': uri,
    };
  }
}

