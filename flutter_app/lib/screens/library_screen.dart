import 'dart:io';
import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../services/spotify_utils.dart';
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
              decoration: const InputDecoration(
                labelText: 'Spotify URL or URI',
                hintText: 'Paste Spotify link or URI',
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'You can paste a Spotify URL (https://open.spotify.com/...)',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
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
        // Convert Spotify URL to URI if needed
        final uri = convertSpotifyUrlToUri(uriController.text);
        await api.updateSong(song.id, nameController.text, uri);
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
        backgroundColor: Colors.teal.shade400,
        foregroundColor: Colors.white,
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
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.error_outline, size: 48, color: Colors.red.shade300),
                      const SizedBox(height: 16),
                      Text('Error: $_error'),
                    ],
                  ),
                )
              : _songs.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.library_music, size: 64, color: Colors.grey.shade400),
                          const SizedBox(height: 16),
                          Text(
                            'No songs in library',
                            style: TextStyle(color: Colors.grey.shade600, fontSize: 16),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Add songs using the + button',
                            style: TextStyle(color: Colors.grey.shade500),
                          ),
                        ],
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.only(top: 8, bottom: 80),
                      itemCount: _songs.length,
                      itemBuilder: (context, index) {
                        final song = _songs[index];
                        final isSpotify = song.uri.startsWith('spotify:');
                        final isLocalFile = song.uri.startsWith('file://');
                        return Card(
                          margin: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 6,
                          ),
                          child: ListTile(
                            leading: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: isSpotify
                                    ? Colors.green.shade100
                                    : Colors.teal.shade100,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Icon(
                                isSpotify
                                    ? Icons.podcasts
                                    : isLocalFile
                                        ? Icons.audio_file
                                        : Icons.music_note,
                                color: isSpotify
                                    ? Colors.green.shade700
                                    : Colors.teal.shade700,
                              ),
                            ),
                            title: Text(
                              song.name,
                              style: const TextStyle(fontWeight: FontWeight.w500),
                            ),
                            subtitle: Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 6,
                                    vertical: 2,
                                  ),
                                  decoration: BoxDecoration(
                                    color: isSpotify
                                        ? Colors.green.shade50
                                        : Colors.grey.shade200,
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Text(
                                    isSpotify ? 'Spotify' : 'Local',
                                    style: TextStyle(
                                      fontSize: 10,
                                      color: isSpotify
                                          ? Colors.green.shade700
                                          : Colors.grey.shade600,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    song.uri,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: Colors.grey.shade600,
                                    ),
                                  ),
                                ),
                              ],
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
                                  child: Row(
                                    children: [
                                      Icon(Icons.edit, size: 20),
                                      SizedBox(width: 8),
                                      Text('Edit'),
                                    ],
                                  ),
                                ),
                                const PopupMenuItem(
                                  value: 'delete',
                                  child: Row(
                                    children: [
                                      Icon(Icons.delete, size: 20, color: Colors.red),
                                      SizedBox(width: 8),
                                      Text('Delete', style: TextStyle(color: Colors.red)),
                                    ],
                                  ),
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
          FloatingActionButton.small(
            heroTag: 'file',
            onPressed: _addFromFile,
            backgroundColor: Colors.teal.shade300,
            child: const Icon(Icons.upload_file, color: Colors.white),
          ),
          const SizedBox(height: 8),
          FloatingActionButton(
            heroTag: 'manual',
            onPressed: _addSong,
            backgroundColor: Colors.teal,
            child: const Icon(Icons.add, color: Colors.white),
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
  String? _convertedUri;

  @override
  void dispose() {
    _nameController.dispose();
    _uriController.dispose();
    super.dispose();
  }

  void _onUriChanged(String value) {
    setState(() {
      if (isSpotifyUrl(value)) {
        _convertedUri = convertSpotifyUrlToUri(value);
      } else {
        _convertedUri = null;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add Spotify Song'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(labelText: 'Song Name'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _uriController,
            onChanged: _onUriChanged,
            decoration: const InputDecoration(
              labelText: 'Spotify URL or URI',
              hintText: 'Paste Spotify link here',
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Paste a Spotify URL like:\nhttps://open.spotify.com/track/...',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
          ),
          if (_convertedUri != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: Row(
                children: [
                  Icon(Icons.check_circle, size: 16, color: Colors.green.shade700),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _convertedUri!,
                      style: TextStyle(
                        fontSize: 11,
                        color: Colors.green.shade800,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
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
              // Convert URL to URI before returning
              final uri = convertSpotifyUrlToUri(_uriController.text);
              Navigator.pop(
                context,
                _SongInput(_nameController.text, uri),
              );
            }
          },
          child: const Text('Add'),
        ),
      ],
    );
  }
}

