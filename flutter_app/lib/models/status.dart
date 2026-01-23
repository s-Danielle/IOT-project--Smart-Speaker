class Status {
  final bool connected;
  final String? chipId;

  Status({required this.connected, this.chipId});

  factory Status.fromJson(Map<String, dynamic> json) {
    return Status(
      connected: json['connected'] ?? false,
      chipId: json['chip_id'],
    );
  }
}

