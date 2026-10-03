/// How the last attempt to play something went, as reported by the speaker.
class LastPlay {
  /// "waiting" (accepted, the sound has not started yet), "ok" or "failed".
  final String result;

  /// Why it failed (Mopidy's own words), if it did.
  final String? reason;

  LastPlay({required this.result, this.reason});

  bool get failed => result == 'failed';

  factory LastPlay.fromJson(Map<String, dynamic> json) {
    return LastPlay(
      result: (json['result'] ?? '').toString(),
      reason: json['reason']?.toString(),
    );
  }
}

/// What the speaker's hardware program (the controller) says about itself.
class ControllerStatus {
  /// False if the controller is not running or has stopped answering.
  final bool alive;

  /// When it is not alive: why, in a sentence.
  final String? problem;

  /// IDLE_NO_CHIP, IDLE_CHIP_LOADED, PLAYING, PAUSED or RECORDING.
  final String state;
  final String? chipName;
  final String? songName;

  /// True only when sound is really coming out.
  final bool playing;
  final int? volume;
  final LastPlay? lastPlay;

  ControllerStatus({
    required this.alive,
    this.problem,
    required this.state,
    this.chipName,
    this.songName,
    required this.playing,
    this.volume,
    this.lastPlay,
  });

  factory ControllerStatus.fromJson(Map<String, dynamic> json) {
    final chip = json['chip'];
    final lastPlay = json['last_play'];
    return ControllerStatus(
      alive: json['alive'] == true,
      problem: json['problem']?.toString(),
      state: (json['state'] ?? '').toString(),
      chipName: chip is Map ? chip['name']?.toString() : null,
      songName: chip is Map ? chip['song_name']?.toString() : null,
      playing: json['playing'] == true,
      volume: json['volume'] is num ? (json['volume'] as num).toInt() : null,
      lastPlay: lastPlay is Map<String, dynamic>
          ? LastPlay.fromJson(lastPlay)
          : null,
    );
  }
}

class Status {
  final bool connected;

  /// "json" or "sqlite": where the speaker keeps its data.
  final String? storage;

  /// Null when talking to a speaker that is too old to report it.
  final ControllerStatus? controller;

  /// Seconds of music played today, or null if the speaker could not say.
  final int? usageSeconds;

  Status({
    required this.connected,
    this.storage,
    this.controller,
    this.usageSeconds,
  });

  factory Status.fromJson(Map<String, dynamic> json) {
    final controller = json['controller'];
    final usage = json['usage'];
    return Status(
      connected: json['connected'] ?? false,
      storage: json['storage']?.toString(),
      controller: controller is Map<String, dynamic>
          ? ControllerStatus.fromJson(controller)
          : null,
      usageSeconds: usage is Map && usage['seconds'] is num
          ? (usage['seconds'] as num).toInt()
          : null,
    );
  }
}
