import 'package:flutter/material.dart';
import '../services/settings_service.dart';
import '../services/api_service.dart';
import '../models/parental_settings.dart';
import '../models/chip.dart';

class ParentalControlsScreen extends StatefulWidget {
  const ParentalControlsScreen({super.key});

  @override
  State<ParentalControlsScreen> createState() => _ParentalControlsScreenState();
}

class _ParentalControlsScreenState extends State<ParentalControlsScreen> {
  ParentalSettings _settings = ParentalSettings.defaults();
  List<SpeakerChip> _chips = [];
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      
      final settingsJson = await api.getParentalSettings();
      final chips = await api.getChips();
      
      setState(() {
        _settings = ParentalSettings.fromJson(settingsJson);
        _chips = chips;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _saveSettings() async {
    setState(() {
      _saving = true;
    });

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      
      await api.updateParentalSettings(_settings.toJson());
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Settings saved')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to save: $e')),
        );
      }
    } finally {
      setState(() {
        _saving = false;
      });
    }
  }

  Future<TimeOfDay?> _pickTime(String currentTime) async {
    final parts = currentTime.split(':');
    final initialTime = TimeOfDay(
      hour: int.parse(parts[0]),
      minute: int.parse(parts[1]),
    );
    
    return showTimePicker(
      context: context,
      initialTime: initialTime,
    );
  }

  String _formatTime(TimeOfDay time) {
    return '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Parental Controls'),
        backgroundColor: theme.colorScheme.inversePrimary,
        actions: [
          if (!_loading)
            IconButton(
              onPressed: _saving ? null : _saveSettings,
              icon: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.error, size: 48, color: theme.colorScheme.error),
                      const SizedBox(height: 16),
                      Text('Failed to load settings'),
                      const SizedBox(height: 8),
                      ElevatedButton(
                        onPressed: _loadSettings,
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(16.0),
                  children: [
                    // Enable/Disable Card
                    Card(
                      child: SwitchListTile(
                        title: const Text('Enable Parental Controls'),
                        subtitle: const Text('Restrict playback and volume'),
                        value: _settings.enabled,
                        onChanged: (value) {
                          setState(() {
                            _settings = _settings.copyWith(enabled: value);
                          });
                        },
                        secondary: Icon(
                          Icons.family_restroom,
                          color: _settings.enabled
                              ? theme.colorScheme.primary
                              : theme.colorScheme.outline,
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Volume Limit Card
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Icon(Icons.volume_up, color: theme.colorScheme.primary),
                                const SizedBox(width: 8),
                                Text(
                                  'Volume Limit',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  '${_settings.volumeLimit}%',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    color: theme.colorScheme.primary,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Slider(
                              value: _settings.volumeLimit.toDouble(),
                              min: 0,
                              max: 100,
                              divisions: 20,
                              label: '${_settings.volumeLimit}%',
                              onChanged: _settings.enabled
                                  ? (value) {
                                      setState(() {
                                        _settings = _settings.copyWith(
                                          volumeLimit: value.round(),
                                        );
                                      });
                                    }
                                  : null,
                            ),
                            Text(
                              'Maximum volume the speaker can reach',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Quiet Hours Card
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Icon(Icons.bedtime, color: theme.colorScheme.primary),
                                const SizedBox(width: 8),
                                Text(
                                  'Quiet Hours',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                const Spacer(),
                                Switch(
                                  value: _settings.quietHours.enabled,
                                  onChanged: _settings.enabled
                                      ? (value) {
                                          setState(() {
                                            _settings = _settings.copyWith(
                                              quietHours: _settings.quietHours.copyWith(
                                                enabled: value,
                                              ),
                                            );
                                          });
                                        }
                                      : null,
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Text(
                              'Block playback during these hours',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                Expanded(
                                  child: OutlinedButton.icon(
                                    onPressed: _settings.enabled && _settings.quietHours.enabled
                                        ? () async {
                                            final time = await _pickTime(_settings.quietHours.start);
                                            if (time != null) {
                                              setState(() {
                                                _settings = _settings.copyWith(
                                                  quietHours: _settings.quietHours.copyWith(
                                                    start: _formatTime(time),
                                                  ),
                                                );
                                              });
                                            }
                                          }
                                        : null,
                                    icon: const Icon(Icons.access_time),
                                    label: Text('Start: ${_settings.quietHours.start}'),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: OutlinedButton.icon(
                                    onPressed: _settings.enabled && _settings.quietHours.enabled
                                        ? () async {
                                            final time = await _pickTime(_settings.quietHours.end);
                                            if (time != null) {
                                              setState(() {
                                                _settings = _settings.copyWith(
                                                  quietHours: _settings.quietHours.copyWith(
                                                    end: _formatTime(time),
                                                  ),
                                                );
                                              });
                                            }
                                          }
                                        : null,
                                    icon: const Icon(Icons.access_time),
                                    label: Text('End: ${_settings.quietHours.end}'),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Daily Limit Card
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Icon(Icons.timer, color: theme.colorScheme.primary),
                                const SizedBox(width: 8),
                                Text(
                                  'Daily Limit',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  _settings.dailyLimitMinutes == 0
                                      ? 'Unlimited'
                                      : '${_settings.dailyLimitMinutes} min',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    color: theme.colorScheme.primary,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Slider(
                              value: _settings.dailyLimitMinutes.toDouble(),
                              min: 0,
                              max: 240,
                              divisions: 24,
                              label: _settings.dailyLimitMinutes == 0
                                  ? 'Unlimited'
                                  : '${_settings.dailyLimitMinutes} min',
                              onChanged: _settings.enabled
                                  ? (value) {
                                      setState(() {
                                        _settings = _settings.copyWith(
                                          dailyLimitMinutes: value.round(),
                                        );
                                      });
                                    }
                                  : null,
                            ),
                            Text(
                              'Maximum playback time per day (0 = unlimited)',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Chip Whitelist/Blacklist Card
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Icon(Icons.nfc, color: theme.colorScheme.primary),
                                const SizedBox(width: 8),
                                Text(
                                  'Chip Access',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            SwitchListTile(
                              title: const Text('Whitelist Mode'),
                              subtitle: const Text('Only allow selected chips'),
                              value: _settings.chipWhitelistMode,
                              onChanged: _settings.enabled
                                  ? (value) {
                                      setState(() {
                                        _settings = _settings.copyWith(
                                          chipWhitelistMode: value,
                                        );
                                      });
                                    }
                                  : null,
                              contentPadding: EdgeInsets.zero,
                            ),
                            const Divider(),
                            const SizedBox(height: 8),
                            Text(
                              _settings.chipWhitelistMode
                                  ? 'Allowed Chips (whitelist)'
                                  : 'Blocked Chips (blacklist)',
                              style: theme.textTheme.bodyMedium?.copyWith(
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            const SizedBox(height: 8),
                            if (_chips.isEmpty)
                              Text(
                                'No chips registered yet',
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              )
                            else
                              ...(_chips.map((chip) {
                                final isInList = _settings.chipWhitelistMode
                                    ? _settings.chipWhitelist.contains(chip.uid)
                                    : _settings.chipBlacklist.contains(chip.uid);
                                
                                return CheckboxListTile(
                                  title: Text(chip.name),
                                  subtitle: chip.songName != null
                                      ? Text(chip.songName!)
                                      : const Text('No song assigned'),
                                  value: isInList,
                                  onChanged: _settings.enabled
                                      ? (value) {
                                          setState(() {
                                            if (_settings.chipWhitelistMode) {
                                              final newList = List<String>.from(_settings.chipWhitelist);
                                              if (value == true && chip.uid != null) {
                                                newList.add(chip.uid!);
                                              } else {
                                                newList.remove(chip.uid);
                                              }
                                              _settings = _settings.copyWith(chipWhitelist: newList);
                                            } else {
                                              final newList = List<String>.from(_settings.chipBlacklist);
                                              if (value == true && chip.uid != null) {
                                                newList.add(chip.uid!);
                                              } else {
                                                newList.remove(chip.uid);
                                              }
                                              _settings = _settings.copyWith(chipBlacklist: newList);
                                            }
                                          });
                                        }
                                      : null,
                                  contentPadding: EdgeInsets.zero,
                                );
                              })),
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
                            Icons.info_outline,
                            color: theme.colorScheme.primary,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              'Changes are applied immediately when saved. Blocked actions will be logged.',
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
}
