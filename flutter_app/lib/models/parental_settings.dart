class QuietHours {
  final bool enabled;
  final String start;
  final String end;

  QuietHours({
    required this.enabled,
    required this.start,
    required this.end,
  });

  factory QuietHours.fromJson(Map<String, dynamic> json) {
    return QuietHours(
      enabled: json['enabled'] ?? false,
      start: json['start'] ?? '21:00',
      end: json['end'] ?? '07:00',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'enabled': enabled,
      'start': start,
      'end': end,
    };
  }

  QuietHours copyWith({
    bool? enabled,
    String? start,
    String? end,
  }) {
    return QuietHours(
      enabled: enabled ?? this.enabled,
      start: start ?? this.start,
      end: end ?? this.end,
    );
  }
}

class ParentalSettings {
  final bool enabled;
  final int volumeLimit;
  final QuietHours quietHours;
  final int dailyLimitMinutes;
  final List<String> chipBlacklist;
  final bool chipWhitelistMode;
  final List<String> chipWhitelist;

  ParentalSettings({
    required this.enabled,
    required this.volumeLimit,
    required this.quietHours,
    required this.dailyLimitMinutes,
    required this.chipBlacklist,
    required this.chipWhitelistMode,
    required this.chipWhitelist,
  });

  factory ParentalSettings.fromJson(Map<String, dynamic> json) {
    return ParentalSettings(
      enabled: json['enabled'] ?? false,
      volumeLimit: json['volume_limit'] ?? 100,
      quietHours: QuietHours.fromJson(json['quiet_hours'] ?? {}),
      dailyLimitMinutes: json['daily_limit_minutes'] ?? 0,
      chipBlacklist: List<String>.from(json['chip_blacklist'] ?? []),
      chipWhitelistMode: json['chip_whitelist_mode'] ?? false,
      chipWhitelist: List<String>.from(json['chip_whitelist'] ?? []),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'enabled': enabled,
      'volume_limit': volumeLimit,
      'quiet_hours': quietHours.toJson(),
      'daily_limit_minutes': dailyLimitMinutes,
      'chip_blacklist': chipBlacklist,
      'chip_whitelist_mode': chipWhitelistMode,
      'chip_whitelist': chipWhitelist,
    };
  }

  ParentalSettings copyWith({
    bool? enabled,
    int? volumeLimit,
    QuietHours? quietHours,
    int? dailyLimitMinutes,
    List<String>? chipBlacklist,
    bool? chipWhitelistMode,
    List<String>? chipWhitelist,
  }) {
    return ParentalSettings(
      enabled: enabled ?? this.enabled,
      volumeLimit: volumeLimit ?? this.volumeLimit,
      quietHours: quietHours ?? this.quietHours,
      dailyLimitMinutes: dailyLimitMinutes ?? this.dailyLimitMinutes,
      chipBlacklist: chipBlacklist ?? this.chipBlacklist,
      chipWhitelistMode: chipWhitelistMode ?? this.chipWhitelistMode,
      chipWhitelist: chipWhitelist ?? this.chipWhitelist,
    );
  }

  /// Factory for default settings
  factory ParentalSettings.defaults() {
    return ParentalSettings(
      enabled: false,
      volumeLimit: 100,
      quietHours: QuietHours(enabled: false, start: '21:00', end: '07:00'),
      dailyLimitMinutes: 0,
      chipBlacklist: [],
      chipWhitelistMode: false,
      chipWhitelist: [],
    );
  }
}
