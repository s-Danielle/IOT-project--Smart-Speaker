import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/settings_service.dart';
import '../models/status.dart';
import 'chips_screen.dart';
import 'library_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Status? _status;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final baseUrl = await SettingsService.getBaseUrl();
      final api = ApiService(baseUrl);
      final status = await api.getStatus();
      setState(() {
        _status = status;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _status = null;
      });
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Smart Speaker'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _refresh,
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Connection Status',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    if (_loading)
                      const CircularProgressIndicator()
                    else if (_error != null)
                      Text('Error: $_error', style: const TextStyle(color: Colors.red))
                    else if (_status != null) ...[
                      Row(
                        children: [
                          Icon(
                            _status!.connected ? Icons.check_circle : Icons.error,
                            color: _status!.connected ? Colors.green : Colors.red,
                          ),
                          const SizedBox(width: 8),
                          Text(_status!.connected ? 'Connected' : 'Disconnected'),
                        ],
                      ),
                      if (_status!.chipId != null) ...[
                        const SizedBox(height: 4),
                        Text('Chip ID: ${_status!.chipId}'),
                      ],
                    ] else
                      const Text('No status available'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const ChipsScreen()),
                );
              },
              child: const Text('Chips'),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LibraryScreen()),
                );
              },
              child: const Text('Library'),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: () async {
                await Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const SettingsScreen()),
                );
                _refresh();
              },
              child: const Text('Settings'),
            ),
          ],
        ),
      ),
    );
  }
}

