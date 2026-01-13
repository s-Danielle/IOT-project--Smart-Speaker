import 'package:flutter/material.dart';
import '../services/settings_service.dart';
import '../services/api_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _controller = TextEditingController();
  String _testResult = '';
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    _loadBaseUrl();
  }

  Future<void> _loadBaseUrl() async {
    final url = await SettingsService.getBaseUrl();
    _controller.text = url;
  }

  Future<void> _saveBaseUrl() async {
    await SettingsService.setBaseUrl(_controller.text);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settings saved')),
      );
    }
  }

  Future<void> _testConnection() async {
    setState(() {
      _testing = true;
      _testResult = '';
    });

    try {
      final api = ApiService(_controller.text);
      final status = await api.getStatus();
      setState(() {
        _testResult = 'Connected: ${status.connected}';
        if (status.chipId != null) {
          _testResult += '\nChip ID: ${status.chipId}';
        }
      });
    } catch (e) {
      setState(() {
        _testResult = 'Error: $e';
      });
    } finally {
      setState(() {
        _testing = false;
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _controller,
              decoration: const InputDecoration(
                labelText: 'Speaker Base URL',
                hintText: 'http://192.168.1.100:8080',
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: _saveBaseUrl,
                    child: const Text('Save'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _testing ? null : _testConnection,
                    child: _testing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Test Connection'),
                  ),
                ),
              ],
            ),
            if (_testResult.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(_testResult),
            ],
          ],
        ),
      ),
    );
  }
}

