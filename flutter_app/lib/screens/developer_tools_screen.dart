import 'package:flutter/material.dart';
import '../services/settings_service.dart';
import '../services/api_service.dart';

class DeveloperToolsScreen extends StatefulWidget {
  const DeveloperToolsScreen({super.key});

  @override
  State<DeveloperToolsScreen> createState() => _DeveloperToolsScreenState();
}

class _DeveloperToolsScreenState extends State<DeveloperToolsScreen> {
  Map<String, dynamic>? _systemInfo;
  Map<String, dynamic>? _i2cInfo;
  Map<String, dynamic>? _gitStatus;
  Map<String, dynamic>? _speakerStatus;
  List<String>? _logs;
  bool _loadingSystem = true;
  bool _loadingI2c = false;
  bool _loadingGit = false;
  bool _loadingLogs = false;
  bool _loadingSpeaker = false;
  bool _showLogs = false;
  String? _actionStatus;

  @override
  void initState() {
    super.initState();
    _loadSystemInfo();
    _loadGitStatus();
    _loadSpeakerStatus();
  }

  Future<ApiService> _getApi() async {
    final baseUrl = await SettingsService.getBaseUrl();
    return ApiService(baseUrl);
  }

  Future<void> _loadSystemInfo() async {
    setState(() => _loadingSystem = true);
    try {
      final api = await _getApi();
      final info = await api.getSystemInfo();
      setState(() {
        _systemInfo = info;
        _loadingSystem = false;
      });
    } catch (e) {
      setState(() {
        _systemInfo = {'error': e.toString()};
        _loadingSystem = false;
      });
    }
  }

  Future<void> _loadI2cDevices() async {
    setState(() => _loadingI2c = true);
    try {
      final api = await _getApi();
      final info = await api.getI2cDevices();
      setState(() {
        _i2cInfo = info;
        _loadingI2c = false;
      });
    } catch (e) {
      setState(() {
        _i2cInfo = {'error': e.toString()};
        _loadingI2c = false;
      });
    }
  }

  Future<void> _loadGitStatus() async {
    setState(() => _loadingGit = true);
    try {
      final api = await _getApi();
      final status = await api.getGitStatus();
      setState(() {
        _gitStatus = status;
        _loadingGit = false;
      });
    } catch (e) {
      setState(() {
        _gitStatus = {'error': e.toString()};
        _loadingGit = false;
      });
    }
  }

  Future<void> _loadLogs() async {
    setState(() => _loadingLogs = true);
    try {
      final api = await _getApi();
      final result = await api.getLogs();
      setState(() {
        _logs = List<String>.from(result['logs'] ?? []);
        _loadingLogs = false;
      });
    } catch (e) {
      setState(() {
        _logs = ['Error loading logs: $e'];
        _loadingLogs = false;
      });
    }
  }

  Future<void> _gitPull() async {
    _showActionStatus('Pulling latest code...');
    try {
      final api = await _getApi();
      final result = await api.gitPull();
      if (result['success'] == true) {
        _showActionStatus('Git pull successful');
        _loadGitStatus();
      } else {
        _showActionStatus('Git pull failed: ${result['stderr']}');
      }
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<void> _loadSpeakerStatus() async {
    setState(() => _loadingSpeaker = true);
    try {
      final api = await _getApi();
      final status = await api.getSpeakerStatus();
      setState(() {
        _speakerStatus = status;
        _loadingSpeaker = false;
      });
    } catch (e) {
      setState(() {
        _speakerStatus = {'status': 'unknown', 'running': false, 'error': e.toString()};
        _loadingSpeaker = false;
      });
    }
  }

  Future<void> _startSpeaker() async {
    final confirmed = await _confirmAction(
      'Start Speaker',
      'Are you sure you want to start the smart speaker hardware controller?',
    );
    if (!confirmed) return;

    _showActionStatus('Starting speaker...');
    try {
      final api = await _getApi();
      final result = await api.startSpeaker();
      _showActionStatus('Speaker ${result['status']}');
      _loadSpeakerStatus();
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<void> _stopSpeaker() async {
    final confirmed = await _confirmAction(
      'Stop Speaker',
      'Are you sure you want to stop the smart speaker hardware controller?',
    );
    if (!confirmed) return;

    _showActionStatus('Stopping speaker...');
    try {
      final api = await _getApi();
      final result = await api.stopSpeaker();
      _showActionStatus('Speaker ${result['status']}');
      _loadSpeakerStatus();
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<void> _restartSpeaker() async {
    final confirmed = await _confirmAction(
      'Restart Speaker',
      'Are you sure you want to restart the smart speaker hardware controller? The API server will stay running.',
    );
    if (!confirmed) return;

    _showActionStatus('Restarting speaker...');
    try {
      final api = await _getApi();
      final result = await api.restartSpeaker();
      _showActionStatus('Speaker ${result['status']}');
      // Wait a moment then refresh status
      await Future.delayed(const Duration(seconds: 2));
      _loadSpeakerStatus();
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<void> _daemonReload() async {
    _showActionStatus('Reloading daemon...');
    try {
      final api = await _getApi();
      final result = await api.daemonReload();
      _showActionStatus('Daemon ${result['status']}');
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<void> _runMain() async {
    final confirmed = await _confirmAction(
      'Run Main',
      'This will start main.py manually. Make sure the service is stopped first.',
    );
    if (!confirmed) return;

    _showActionStatus('Starting main.py...');
    try {
      final api = await _getApi();
      final result = await api.runMain();
      _showActionStatus('main.py ${result['status']}');
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<void> _rebootPi() async {
    final confirmed = await _confirmAction(
      'Reboot Raspberry Pi',
      'Are you sure you want to reboot the Raspberry Pi? The speaker will be unavailable for a few minutes.',
    );
    if (!confirmed) return;

    _showActionStatus('Rebooting...');
    try {
      final api = await _getApi();
      await api.rebootPi();
      _showActionStatus('Reboot initiated');
    } catch (e) {
      _showActionStatus('Error: $e');
    }
  }

  Future<bool> _confirmAction(String title, String message) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(title),
            content: Text(message),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Cancel'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Confirm'),
              ),
            ],
          ),
        ) ??
        false;
  }

  void _showActionStatus(String status) {
    setState(() => _actionStatus = status);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(status)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Developer Tools'),
        backgroundColor: theme.colorScheme.inversePrimary,
        actions: [
          IconButton(
            onPressed: () {
              _loadSystemInfo();
              _loadGitStatus();
            },
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          // System Info Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.memory, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        'System Information',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const Spacer(),
                      if (_loadingSystem)
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_systemInfo != null) ...[
                    _buildInfoRow('Temperature', _systemInfo!['temperature'] ?? 'N/A'),
                    _buildInfoRow('Uptime', _systemInfo!['uptime'] ?? 'N/A'),
                    if (_systemInfo!['memory'] != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        'Memory:',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          _systemInfo!['memory'],
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 10,
                          ),
                        ),
                      ),
                    ],
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // I2C Devices Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.developer_board, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        'I2C Devices',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const Spacer(),
                      if (_loadingI2c)
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      else
                        IconButton(
                          onPressed: _loadI2cDevices,
                          icon: const Icon(Icons.search),
                          tooltip: 'Scan I2C bus',
                        ),
                    ],
                  ),
                  if (_i2cInfo != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(8),
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        _i2cInfo!['output'] ?? _i2cInfo!['error'] ?? 'No data',
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 10,
                        ),
                      ),
                    ),
                  ] else
                    Text(
                      'Tap the search icon to scan I2C devices',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // Git Status Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.source, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        'Git Status',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const Spacer(),
                      if (_loadingGit)
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_gitStatus != null) ...[
                    _buildInfoRow('Branch', _gitStatus!['branch'] ?? 'unknown'),
                    if (_gitStatus!['status']?.isNotEmpty == true) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.all(8),
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          _gitStatus!['status'],
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 11,
                          ),
                        ),
                      ),
                    ] else
                      Text(
                        'Working tree clean',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: Colors.green,
                        ),
                      ),
                  ],
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _gitPull,
                      icon: const Icon(Icons.download),
                      label: const Text('Git Pull'),
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // Speaker Controls Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.speaker, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        'Speaker Controls',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const Spacer(),
                      if (_loadingSpeaker)
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      else
                        IconButton(
                          onPressed: _loadSpeakerStatus,
                          icon: const Icon(Icons.refresh),
                          tooltip: 'Refresh status',
                        ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  // Speaker Status Indicator
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: _speakerStatus?['running'] == true
                          ? Colors.green.withValues(alpha: 0.1)
                          : Colors.orange.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: _speakerStatus?['running'] == true
                            ? Colors.green
                            : Colors.orange,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _speakerStatus?['running'] == true
                              ? Icons.check_circle
                              : Icons.pause_circle,
                          color: _speakerStatus?['running'] == true
                              ? Colors.green
                              : Colors.orange,
                          size: 16,
                        ),
                        const SizedBox(width: 8),
                        Text(
                          'Hardware: ${_speakerStatus?['status'] ?? 'unknown'}',
                          style: TextStyle(
                            color: _speakerStatus?['running'] == true
                                ? Colors.green
                                : Colors.orange,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Control the hardware controller (NFC, buttons, LEDs). The API server stays running.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      if (_speakerStatus?['running'] != true)
                        OutlinedButton.icon(
                          onPressed: _startSpeaker,
                          icon: const Icon(Icons.play_arrow),
                          label: const Text('Start'),
                        )
                      else
                        OutlinedButton.icon(
                          onPressed: _stopSpeaker,
                          icon: const Icon(Icons.stop),
                          label: const Text('Stop'),
                        ),
                      OutlinedButton.icon(
                        onPressed: _restartSpeaker,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Restart'),
                      ),
                      OutlinedButton.icon(
                        onPressed: _daemonReload,
                        icon: const Icon(Icons.sync),
                        label: const Text('Daemon Reload'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // Logs Card
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: Icon(Icons.article, color: theme.colorScheme.primary),
                  title: const Text('System Logs'),
                  trailing: _loadingLogs
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Icon(
                          _showLogs ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                        ),
                  onTap: () {
                    setState(() {
                      _showLogs = !_showLogs;
                    });
                    if (_showLogs && _logs == null) {
                      _loadLogs();
                    }
                  },
                ),
                if (_showLogs) ...[
                  const Divider(height: 1),
                  Container(
                    height: 300,
                    padding: const EdgeInsets.all(8),
                    child: _logs == null
                        ? const Center(child: CircularProgressIndicator())
                        : SingleChildScrollView(
                            child: Text(
                              _logs!.join('\n'),
                              style: const TextStyle(
                                fontFamily: 'monospace',
                                fontSize: 10,
                              ),
                            ),
                          ),
                  ),
                  Padding(
                    padding: const EdgeInsets.all(8.0),
                    child: SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _loadLogs,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Refresh Logs'),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),

          const SizedBox(height: 16),

          // Reboot Card
          Card(
            color: theme.colorScheme.errorContainer.withValues(alpha: 0.3),
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.power_settings_new, color: theme.colorScheme.error),
                      const SizedBox(width: 8),
                      Text(
                        'System',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _rebootPi,
                      icon: const Icon(Icons.restart_alt),
                      label: const Text('Reboot Raspberry Pi'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: theme.colorScheme.error,
                        foregroundColor: theme.colorScheme.onError,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 24),

          // Info
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.warning_amber,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'These tools are for advanced users. Use with caution.',
                    style: TextStyle(
                      color: theme.colorScheme.onSurfaceVariant,
                      fontSize: 13,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}
