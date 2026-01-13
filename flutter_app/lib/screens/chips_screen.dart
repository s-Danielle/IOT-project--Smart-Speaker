import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../models/chip.dart';
import '../models/song.dart';

class ChipsScreen extends StatefulWidget {
  const ChipsScreen({super.key});

  @override
  State<ChipsScreen> createState() => _ChipsScreenState();
}

class _ChipsScreenState extends State<ChipsScreen> {
  List<SpeakerChip> _chips = [];
  List<Song> _songs = [];
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      final chips = await api.getChips();
      final songs = await api.getLibrary();
      setState(() {
        _chips = chips;
        _songs = songs;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  Future<void> _renameChip(SpeakerChip chip) async {
    final controller = TextEditingController(text: chip.name);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename Chip'),
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
        await api.updateChip(chip.id, name: result);
        _loadData();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  Future<void> _assignSong(SpeakerChip chip) async {
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
        await api.updateChip(chip.id, songId: result.id);
        _loadData();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  Future<void> _resetAssignment(SpeakerChip chip) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Reset Assignment'),
        content: Text('Remove song assignment from "${chip.name}"?'),
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
        await api.resetChipAssignment(chip.id);
        _loadData();
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
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chips'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _loadData,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Error: $_error'))
              : _chips.isEmpty
                  ? const Center(child: Text('No chips found'))
                  : ListView.builder(
                      itemCount: _chips.length,
                      itemBuilder: (context, index) {
                        final chip = _chips[index];
                        return Card(
                          margin: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 4,
                          ),
                          child: ListTile(
                            title: Text(chip.name.isEmpty ? chip.id : chip.name),
                            subtitle: Text(
                              chip.songName ?? 'Empty',
                              style: TextStyle(
                                color: chip.songName != null
                                    ? null
                                    : Colors.grey,
                              ),
                            ),
                            trailing: PopupMenuButton<String>(
                              onSelected: (value) {
                                switch (value) {
                                  case 'rename':
                                    _renameChip(chip);
                                  case 'assign':
                                    _assignSong(chip);
                                  case 'reset':
                                    _resetAssignment(chip);
                                }
                              },
                              itemBuilder: (_) => [
                                const PopupMenuItem(
                                  value: 'rename',
                                  child: Text('Rename'),
                                ),
                                const PopupMenuItem(
                                  value: 'assign',
                                  child: Text('Assign Song'),
                                ),
                                const PopupMenuItem(
                                  value: 'reset',
                                  child: Text('Reset Assignment'),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
    );
  }
}

