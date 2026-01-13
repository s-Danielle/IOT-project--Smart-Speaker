import 'dart:io';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../models/song.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  List<Song> _songs = [];
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSongs();
  }

  Future<void> _loadSongs() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      final songs = await api.getLibrary();
      setState(() {
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

  Future<void> _addSong() async {
    final result = await showDialog<_SongInput>(
      context: context,
      builder: (context) => const _AddSongDialog(),
    );

    if (result != null) {
      try {
        final baseUrl = await SettingsService.getBaseUrl();
        final api = ApiService(baseUrl);
        await api.createSong(result.name, result.uri);
        _loadSongs();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  Future<void> _addFromFile() async {
    final result = await FilePicker.platform.pickFiles();
    if (result == null || result.files.isEmpty) return;
    if (!mounted) return;

    final file = result.files.first;
    if (file.path == null) return;

    final nameController = TextEditingController(
      text: file.name.replaceAll(RegExp(r'\.[^.]+$'), ''),
    );

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add Song from File'),
        content: TextField(
          controller: nameController,
          decoration: const InputDecoration(labelText: 'Song Name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Upload'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);

      // Upload file and get URI
      final uri = await api.uploadFile(File(file.path!));

      // Create library entry
      await api.createSong(nameController.text, uri);
      _loadSongs();

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Song added')),
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

  Future<void> _editSong(Song song) async {
    final nameController = TextEditingController(text: song.name);
    final uriController = TextEditingController(text: song.uri);

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Edit Song'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: uriController,
              decoration: const InputDecoration(labelText: 'URI'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        final baseUrl = await SettingsService.getBaseUrl();
        final api = ApiService(baseUrl);
        await api.updateSong(song.id, nameController.text, uriController.text);
        _loadSongs();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: $e')),
          );
        }
      }
    }
  }

  Future<void> _deleteSong(Song song) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Song'),
        content: Text('Delete "${song.name}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        final baseUrl = await SettingsService.getBaseUrl();
        final api = ApiService(baseUrl);
        await api.deleteSong(song.id);
        _loadSongs();
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
        title: const Text('Library'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _loadSongs,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Error: $_error'))
              : _songs.isEmpty
                  ? const Center(child: Text('No songs in library'))
                  : ListView.builder(
                      itemCount: _songs.length,
                      itemBuilder: (context, index) {
                        final song = _songs[index];
                        return Card(
                          margin: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 4,
                          ),
                          child: ListTile(
                            title: Text(song.name),
                            subtitle: Text(
                              song.uri,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            trailing: PopupMenuButton<String>(
                              onSelected: (value) {
                                switch (value) {
                                  case 'edit':
                                    _editSong(song);
                                  case 'delete':
                                    _deleteSong(song);
                                }
                              },
                              itemBuilder: (_) => [
                                const PopupMenuItem(
                                  value: 'edit',
                                  child: Text('Edit'),
                                ),
                                const PopupMenuItem(
                                  value: 'delete',
                                  child: Text('Delete'),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FloatingActionButton(
            heroTag: 'file',
            onPressed: _addFromFile,
            child: const Icon(Icons.upload_file),
          ),
          const SizedBox(height: 8),
          FloatingActionButton(
            heroTag: 'manual',
            onPressed: _addSong,
            child: const Icon(Icons.add),
          ),
        ],
      ),
    );
  }
}

class _SongInput {
  final String name;
  final String uri;
  _SongInput(this.name, this.uri);
}

class _AddSongDialog extends StatefulWidget {
  const _AddSongDialog();

  @override
  State<_AddSongDialog> createState() => _AddSongDialogState();
}

class _AddSongDialogState extends State<_AddSongDialog> {
  final _nameController = TextEditingController();
  final _uriController = TextEditingController();

  @override
  void dispose() {
    _nameController.dispose();
    _uriController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add Song'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(labelText: 'Name'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _uriController,
            decoration: const InputDecoration(
              labelText: 'URI',
              hintText: 'spotify:track:... or file path',
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: () {
            if (_nameController.text.isNotEmpty &&
                _uriController.text.isNotEmpty) {
              Navigator.pop(
                context,
                _SongInput(_nameController.text, _uriController.text),
              );
            }
          },
          child: const Text('Add'),
        ),
      ],
    );
  }
}

