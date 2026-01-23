import 'dart:io';
import 'package:flutter/material.dart';
import 'package:nfc_manager/nfc_manager.dart';
import 'package:nfc_manager/nfc_manager_android.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../models/chip.dart';
import '../models/song.dart';

class ScanChipScreen extends StatefulWidget {
  const ScanChipScreen({super.key});

  @override
  State<ScanChipScreen> createState() => _ScanChipScreenState();
}

class _ScanChipScreenState extends State<ScanChipScreen> {
  bool _isNfcAvailable = false;
  bool _isScanning = false;
  String? _scannedId;
  SpeakerChip? _matchedChip;
  List<Song> _songs = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _checkNfcAvailability();
  }

  Future<void> _checkNfcAvailability() async {
    final availability = await NfcManager.instance.checkAvailability();
    setState(() {
      _isNfcAvailable = availability == NfcAvailability.enabled;
    });
    if (_isNfcAvailable) {
      _loadSongs();
    }
  }

  Future<void> _loadSongs() async {
    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      final songs = await api.getLibrary();
      setState(() {
        _songs = songs;
      });
    } catch (e) {
      // Songs will be empty, that's ok
    }
  }

  String _extractTagId(NfcTag tag) {
    try {
      // Android: use NfcTagAndroid to get the ID
      if (Platform.isAndroid) {
        final androidTag = NfcTagAndroid.from(tag);
        if (androidTag != null) {
          return androidTag.id
              .map((b) => b.toRadixString(16).padLeft(2, '0'))
              .join('')
              .toUpperCase();
        }
      }
      
      // Fallback: generate from hash
      return 'TAG${tag.hashCode.toRadixString(16).toUpperCase()}';
    } catch (e) {
      return 'TAG${tag.hashCode.toRadixString(16).toUpperCase()}';
    }
  }

  Future<void> _startScanning() async {
    setState(() {
      _isScanning = true;
      _scannedId = null;
      _matchedChip = null;
      _error = null;
    });

    try {
      await NfcManager.instance.startSession(
        pollingOptions: {
          NfcPollingOption.iso14443,
          NfcPollingOption.iso15693,
        },
        onDiscovered: (NfcTag tag) async {
          final chipId = _extractTagId(tag);

          await NfcManager.instance.stopSession();

          if (mounted) {
            setState(() {
              _scannedId = chipId;
              _isScanning = false;
            });
            _syncChip(chipId);
          }
        },
      );
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isScanning = false;
      });
    }
  }

  Future<void> _stopScanning() async {
    await NfcManager.instance.stopSession();
    setState(() {
      _isScanning = false;
    });
  }

  Future<void> _syncChip(String chipUid) async {
    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      final chips = await api.getChips();

      // Match by UID (the NFC chip's unique identifier), not by internal id
      final match = chips.where((c) => c.uid == chipUid).firstOrNull;

      setState(() {
        _matchedChip = match;
      });

      if (match == null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('New chip detected: $chipUid')),
        );
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
      });
    }
  }

  Future<void> _renameChip() async {
    if (_matchedChip == null && _scannedId == null) return;

    final isNewChip = _matchedChip == null;
    final controller = TextEditingController(text: _matchedChip?.name ?? '');
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(isNewChip ? 'Setup New Chip' : 'Rename Chip'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: 'Name'),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (result != null && result.isNotEmpty) {
      try {
        final baseUrl = await SettingsService.getBaseUrl();
        final api = ApiService(baseUrl);
        
        if (isNewChip) {
          // NEW chip - call POST /chips to register it first
          final newChip = await api.createChip(_scannedId!, name: result);
          setState(() {
            _matchedChip = newChip;
          });
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Chip registered successfully')),
            );
          }
        } else {
          // EXISTING chip - call PUT /chips/{id} to update it
          await api.updateChip(_matchedChip!.id, name: result);
          _syncChip(_scannedId!);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Chip renamed')),
            );
          }
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  Future<void> _assignSong() async {
    // Only allow assigning songs to registered chips
    if (_matchedChip == null || _scannedId == null) return;

    final result = await showDialog<Song>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Assign Song'),
        content: SizedBox(
          width: double.maxFinite,
          child: _songs.isEmpty
              ? const Text('No songs in library')
              : ListView.builder(
                  shrinkWrap: true,
                  itemCount: _songs.length,
                  itemBuilder: (context, index) {
                    final song = _songs[index];
                    return ListTile(
                      title: Text(song.name),
                      subtitle: Text(song.uri),
                      onTap: () => Navigator.pop(context, song),
                    );
                  },
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );

    if (result != null) {
      try {
        final baseUrl = await SettingsService.getBaseUrl();
        final api = ApiService(baseUrl);
        // Use internal chip id for API call
        await api.updateChip(_matchedChip!.id, songId: result.id);
        // Use UID for syncing (to match by uid)
        _syncChip(_scannedId!);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Assigned "${result.name}"')),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  Future<void> _resetAssignment() async {
    if (_matchedChip == null || _scannedId == null) return;

    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Reset Assignment'),
        content: Text('Remove song from "${_matchedChip!.name}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Reset'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        final baseUrl = await SettingsService.getBaseUrl();
        final api = ApiService(baseUrl);
        // Use internal chip id for API call
        await api.resetChipAssignment(_matchedChip!.id);
        // Use UID for syncing (to match by uid)
        _syncChip(_scannedId!);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Assignment reset')),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  @override
  void dispose() {
    NfcManager.instance.stopSession();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan Chip'),
        backgroundColor: theme.colorScheme.primary,
        foregroundColor: theme.colorScheme.onPrimary,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!_isNfcAvailable) ...[
              Card(
                color: Colors.orange.shade100,
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Row(
                    children: [
                      Icon(Icons.warning, color: Colors.orange.shade700),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'NFC is not available on this device',
                          style: TextStyle(color: Colors.orange.shade900),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ] else ...[
              Expanded(
                child: Card(
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(16),
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: _isScanning
                            ? [Colors.blue.shade400, Colors.blue.shade600]
                            : _scannedId != null
                                ? [Colors.green.shade400, Colors.green.shade600]
                                : [Colors.grey.shade300, Colors.grey.shade400],
                      ),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(24.0),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            _isScanning
                                ? Icons.nfc
                                : _scannedId != null
                                    ? Icons.check_circle
                                    : Icons.nfc_outlined,
                            size: 80,
                            color: Colors.white,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            _isScanning
                                ? 'Hold your phone near the chip...'
                                : _scannedId != null
                                    ? 'Chip Scanned!'
                                    : 'Tap button to start scanning',
                            style: const TextStyle(
                              fontSize: 18,
                              color: Colors.white,
                              fontWeight: FontWeight.w500,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          if (_isScanning) ...[
                            const SizedBox(height: 16),
                            const CircularProgressIndicator(color: Colors.white),
                          ],
                          if (_error != null) ...[
                            const SizedBox(height: 16),
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.red.shade100,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                'Error: $_error',
                                style: TextStyle(color: Colors.red.shade900),
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              if (_scannedId != null) ...[
                const SizedBox(height: 16),
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
                            Expanded(
                              child: Text(
                                'Chip ID: $_scannedId',
                                style: const TextStyle(
                                  fontFamily: 'monospace',
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        if (_matchedChip != null) ...[
                          Text('Name: ${_matchedChip!.name.isEmpty ? "(unnamed)" : _matchedChip!.name}'),
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              Icon(
                                _matchedChip!.songName != null
                                    ? Icons.music_note
                                    : Icons.music_off,
                                size: 16,
                                color: _matchedChip!.songName != null
                                    ? theme.colorScheme.primary
                                    : Colors.grey,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                _matchedChip!.songName ?? 'No song assigned',
                                style: TextStyle(
                                  color: _matchedChip!.songName != null ? null : Colors.grey,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              ElevatedButton.icon(
                                onPressed: _renameChip,
                                icon: const Icon(Icons.edit, size: 18),
                                label: const Text('Rename'),
                              ),
                              ElevatedButton.icon(
                                onPressed: _assignSong,
                                icon: const Icon(Icons.music_note, size: 18),
                                label: const Text('Assign'),
                              ),
                              if (_matchedChip!.songId != null)
                                ElevatedButton.icon(
                                  onPressed: _resetAssignment,
                                  icon: const Icon(Icons.clear, size: 18),
                                  label: const Text('Reset'),
                                ),
                            ],
                          ),
                        ] else ...[
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.orange.shade50,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              children: [
                                Icon(Icons.info, color: Colors.orange.shade700, size: 20),
                                const SizedBox(width: 8),
                                Text(
                                  'New chip - not yet registered',
                                  style: TextStyle(color: Colors.orange.shade900),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 12),
                          ElevatedButton.icon(
                            onPressed: _renameChip,
                            icon: const Icon(Icons.add, size: 18),
                            label: const Text('Setup Chip'),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: theme.colorScheme.primary,
                              foregroundColor: theme.colorScheme.onPrimary,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],

              const SizedBox(height: 16),
              SizedBox(
                height: 56,
                child: ElevatedButton.icon(
                  onPressed: _isScanning ? _stopScanning : _startScanning,
                  icon: Icon(_isScanning ? Icons.stop : Icons.nfc, size: 24),
                  label: Text(
                    _isScanning ? 'Stop Scanning' : 'Start Scanning',
                    style: const TextStyle(fontSize: 16),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _isScanning ? Colors.red : theme.colorScheme.primary,
                    foregroundColor: Colors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
