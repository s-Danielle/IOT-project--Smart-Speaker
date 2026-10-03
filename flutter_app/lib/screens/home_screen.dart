import 'dart:async';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../models/status.dart';
import 'chips_screen.dart';
import 'library_screen.dart';
import 'settings_screen.dart';
import 'wifi_setup_screen.dart';
// The real scan screen needs dart:io + nfc_manager, which don't exist on
// web, so the web build gets a stub instead.
import 'scan_chip_screen_stub.dart' if (dart.library.io) 'scan_chip_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Status? _status;
  String? _error;
  bool _loading = false;

  /// Asks the speaker again every few seconds while this screen is the one
  /// being shown, so "what is playing" stays current.
  Timer? _timer;

  /// Quiet refreshes that failed in a row. One missed answer is not shown as an error.
  int _quietFailures = 0;

  @override
  void initState() {
    super.initState();
    _refresh();
    _startTimer();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (!_loading) _refresh(quiet: true);
    });
  }

  /// Opens another screen. The home screen stops asking the speaker while
  /// another screen is on top, and refreshes when it comes back.
  Future<void> _open(Widget screen) async {
    _timer?.cancel();
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => screen),
    );
    if (!mounted) return;
    _startTimer();
    _refresh();
  }

  Future<void> _refresh({bool quiet = false}) async {
    if (!quiet) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      final status = await api.getStatus();
      if (!mounted) return;
      setState(() {
        _status = status;
        _error = null;
      });
      _quietFailures = 0;
    } catch (e) {
      if (!mounted) return;
      _quietFailures++;
      if (!quiet || _quietFailures >= 2) {
        setState(() {
          _error = e.toString();
          _status = null;
        });
      }
    } finally {
      if (mounted && !quiet) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  /// "under a minute", "1 min", "12 min"
  static String _minutes(int seconds) {
    if (seconds < 60) return 'under a minute';
    return '${seconds ~/ 60} min';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.speaker, color: theme.colorScheme.primary),
            const SizedBox(width: 8),
            const Text('Smart Speaker'),
          ],
        ),
        backgroundColor: theme.colorScheme.inversePrimary,
        actions: [
          IconButton(
            icon: _loading
                ? SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: theme.colorScheme.primary,
                    ),
                  )
                : const Icon(Icons.refresh),
            onPressed: _loading ? null : _refresh,
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Connection Status Card
            Card(
              child: Container(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: _status?.connected == true
                        ? [
                            Colors.green.shade400,
                            Colors.green.shade600,
                          ]
                        : _error != null
                            ? [
                                Colors.red.shade400,
                                Colors.red.shade600,
                              ]
                            : [
                                theme.colorScheme.primary,
                                theme.colorScheme.secondary,
                              ],
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(20.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              _status?.connected == true
                                  ? Icons.wifi
                                  : _error != null
                                      ? Icons.wifi_off
                                      : Icons.wifi_find,
                              color: Colors.white,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  _loading
                                      ? 'Connecting...'
                                      : _status?.connected == true
                                          ? 'Connected'
                                          : _error != null
                                              ? 'Connection Error'
                                              : 'Not Connected',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                if (_error != null && !_loading)
                                  Text(
                                    _error!,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      color: Colors.white.withValues(alpha: 0.9),
                                      fontSize: 13,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          if (_loading)
                            const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),

            // What the speaker is doing right now
            if (_status?.controller != null) ...[
              const SizedBox(height: 12),
              _buildSpeakerCard(theme, _status!),
            ],

            // WiFi setup prompt when speaker is unreachable
            if (_error != null && !_loading) ...[
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => _open(const WifiSetupScreen()),
                  icon: const Icon(Icons.wifi_tethering),
                  label: const Text('Set up WiFi'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.primary,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ],

            const SizedBox(height: 24),

            // Scan Chip - Primary Action (phone NFC; not available on web)
            if (!kIsWeb) ...[
              SizedBox(
                height: 64,
                child: ElevatedButton.icon(
                  onPressed: () => _open(const ScanChipScreen()),
                  icon: const Icon(Icons.nfc, size: 28),
                  label: const Text(
                    'Scan Chip',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: theme.colorScheme.onPrimary,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],

            // Navigation Grid
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.3,
              children: [
                _buildNavCard(
                  context,
                  icon: Icons.memory,
                  label: 'Chips',
                  color: Colors.orange,
                  onTap: () => _open(const ChipsScreen()),
                ),
                _buildNavCard(
                  context,
                  icon: Icons.library_music,
                  label: 'Library',
                  color: Colors.teal,
                  onTap: () => _open(const LibraryScreen()),
                ),
                _buildNavCard(
                  context,
                  icon: Icons.settings,
                  label: 'Settings',
                  color: Colors.blueGrey,
                  onTap: () => _open(const SettingsScreen()),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// What the speaker is doing: playing, ready, waiting; the volume; the time
  /// played today; and a warning if the last song could not be played.
  Widget _buildSpeakerCard(ThemeData theme, Status status) {
    final controller = status.controller!;

    IconData icon;
    String headline;
    String? detail;
    Color color;

    if (!controller.alive) {
      icon = Icons.error_outline;
      headline = 'The speaker is not running';
      detail = controller.problem;
      color = Colors.red;
    } else {
      final song = controller.songName ?? controller.chipName;
      switch (controller.state) {
        case 'PLAYING':
          icon = controller.playing ? Icons.play_circle : Icons.hourglass_top;
          headline = controller.playing ? 'Playing' : 'Starting...';
          detail = song;
          color = Colors.green;
          break;
        case 'PAUSED':
          icon = Icons.pause_circle;
          headline = 'Paused';
          detail = song;
          color = Colors.orange;
          break;
        case 'RECORDING':
          icon = Icons.mic;
          headline = 'Recording';
          detail = null;
          color = Colors.red;
          break;
        case 'IDLE_CHIP_LOADED':
          icon = Icons.nfc;
          headline = 'Ready: ${controller.chipName ?? 'chip'}';
          detail = 'Press Play on the speaker';
          color = theme.colorScheme.primary;
          break;
        default:
          icon = Icons.nfc;
          headline = 'Waiting for a chip';
          detail = 'Put a chip on the speaker';
          color = theme.colorScheme.primary;
      }
    }

    final facts = <String>[];
    if (controller.alive && controller.volume != null) {
      facts.add('Volume ${controller.volume}%');
    }
    if (status.usageSeconds != null) {
      facts.add('Played today: ${_minutes(status.usageSeconds!)}');
    }
    final lastPlay = controller.lastPlay;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 36, color: color),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        headline,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      if (detail != null && detail.isNotEmpty)
                        Text(
                          detail,
                          style: TextStyle(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
            if (facts.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                facts.join('   ·   '),
                style: TextStyle(
                  color: theme.colorScheme.onSurfaceVariant,
                  fontSize: 13,
                ),
              ),
            ],
            if (lastPlay != null && lastPlay.failed) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.orange.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange.shade200),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.warning_amber, color: Colors.orange.shade700),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'The last song could not be played'
                        '${lastPlay.reason == null ? '' : '\n${lastPlay.reason}'}',
                        style: TextStyle(
                          color: Colors.orange.shade900,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildNavCard(
    BuildContext context, {
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                color.withValues(alpha: 0.8),
                color,
              ],
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 36, color: Colors.white),
                const SizedBox(height: 8),
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
