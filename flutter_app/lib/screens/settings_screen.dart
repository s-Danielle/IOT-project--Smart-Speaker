import 'package:flutter/material.dart';
import '../services/settings_service.dart';
import '../services/api_service.dart';
import 'parental_controls_screen.dart';
import 'developer_tools_screen.dart';
import 'wifi_setup_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _controller = TextEditingController();
  final _tokenController = TextEditingController();
  bool _tokenHidden = true;
  bool _checkingToken = false;
  String _tokenResult = '';
  String _testResult = '';
  bool _testing = false;
  bool _showAdvanced = false;
  bool _isCustomUrl = false;

  @override
  void initState() {
    super.initState();
    _loadBaseUrl();
    _loadToken();
  }

  Future<void> _loadToken() async {
    _tokenController.text = await SettingsService.getToken();
    if (mounted) setState(() {});
  }

  Future<void> _saveToken() async {
    await SettingsService.setToken(_tokenController.text);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Token saved')),
      );
    }
  }

  /// Saves the token, then asks the speaker whether it accepts it.
  Future<void> _checkToken() async {
    setState(() {
      _checkingToken = true;
      _tokenResult = '';
    });
    try {
      await SettingsService.setToken(_tokenController.text);
      final baseUrl = await SettingsService.getBaseUrl();
      await ApiService(baseUrl).checkToken();
      if (mounted) setState(() => _tokenResult = 'ok');
    } catch (e) {
      final message = e is ApiException && e.isTokenProblem
          ? 'The speaker did not accept this token.'
          : '$e';
      if (mounted) setState(() => _tokenResult = 'error:$message');
    } finally {
      if (mounted) setState(() => _checkingToken = false);
    }
  }

  Future<void> _loadBaseUrl() async {
    final url = await SettingsService.getBaseUrl();
    _controller.text = url;
    setState(() {
      _isCustomUrl = url != SettingsService.defaultBaseUrl;
      _showAdvanced = _isCustomUrl;
    });
  }

  Future<void> _saveBaseUrl() async {
    await SettingsService.setBaseUrl(_controller.text);
    setState(() {
      _isCustomUrl = _controller.text != SettingsService.defaultBaseUrl;
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settings saved')),
      );
    }
  }

  Future<void> _resetToDefault() async {
    await SettingsService.resetToDefault();
    _controller.text = SettingsService.defaultBaseUrl;
    setState(() {
      _isCustomUrl = false;
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Reset to default')),
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
        _testResult = status.connected ? 'success' : 'disconnected';
      });
    } catch (e) {
      setState(() {
        _testResult = 'error:$e';
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
    _tokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        backgroundColor: theme.colorScheme.inversePrimary,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: [
          // Connection Status Card
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
                        'Speaker Connection',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          Icons.link,
                          size: 20,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _controller.text.isEmpty
                                ? SettingsService.defaultBaseUrl
                                : _controller.text,
                            style: TextStyle(
                              fontFamily: 'monospace',
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ),
                        if (_isCustomUrl)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.tertiaryContainer,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              'Custom',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onTertiaryContainer,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _testing ? null : _testConnection,
                      icon: _testing
                          ? SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: theme.colorScheme.onPrimary,
                              ),
                            )
                          : const Icon(Icons.wifi_find),
                      label: Text(_testing ? 'Testing...' : 'Test Connection'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: theme.colorScheme.primary,
                        foregroundColor: theme.colorScheme.onPrimary,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                  if (_testResult.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: _testResult == 'success'
                            ? Colors.green.shade50
                            : Colors.red.shade50,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: _testResult == 'success'
                              ? Colors.green.shade200
                              : Colors.red.shade200,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _testResult == 'success'
                                ? Icons.check_circle
                                : Icons.error,
                            color: _testResult == 'success'
                                ? Colors.green
                                : Colors.red,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _testResult == 'success'
                                  ? 'Connected successfully!'
                                  : _testResult.startsWith('error:')
                                      ? 'Connection failed'
                                      : 'Speaker disconnected',
                              style: TextStyle(
                                color: _testResult == 'success'
                                    ? Colors.green.shade700
                                    : Colors.red.shade700,
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
          ),

          const SizedBox(height: 16),

          // Speaker token: needed for every change made from the app
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.vpn_key, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        'Speaker Token',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Changing chips, songs and settings needs the speaker\'s token. '
                    'It is in the file SECRETS on the speaker, as DEBUG_TOKEN. '
                    'Looking at things does not need it.',
                    style: TextStyle(
                      color: theme.colorScheme.onSurfaceVariant,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _tokenController,
                    obscureText: _tokenHidden,
                    autocorrect: false,
                    enableSuggestions: false,
                    decoration: InputDecoration(
                      labelText: 'Token',
                      border: const OutlineInputBorder(),
                      prefixIcon: const Icon(Icons.vpn_key),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _tokenHidden ? Icons.visibility : Icons.visibility_off,
                        ),
                        onPressed: () {
                          setState(() {
                            _tokenHidden = !_tokenHidden;
                          });
                        },
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _saveToken,
                          icon: const Icon(Icons.save),
                          label: const Text('Save'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: _checkingToken ? null : _checkToken,
                          icon: const Icon(Icons.verified_user),
                          label: Text(_checkingToken ? 'Checking...' : 'Check'),
                        ),
                      ),
                    ],
                  ),
                  if (_tokenResult.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Icon(
                          _tokenResult == 'ok' ? Icons.check_circle : Icons.error,
                          color: _tokenResult == 'ok' ? Colors.green : Colors.red,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _tokenResult == 'ok'
                                ? 'The speaker accepted the token.'
                                : _tokenResult.substring('error:'.length),
                            style: TextStyle(
                              color: _tokenResult == 'ok'
                                  ? Colors.green.shade700
                                  : Colors.red.shade700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // Advanced Settings
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: Icon(
                    Icons.settings,
                    color: theme.colorScheme.secondary,
                  ),
                  title: const Text('Advanced Settings'),
                  trailing: Icon(
                    _showAdvanced
                        ? Icons.keyboard_arrow_up
                        : Icons.keyboard_arrow_down,
                  ),
                  onTap: () {
                    setState(() {
                      _showAdvanced = !_showAdvanced;
                    });
                  },
                ),
                if (_showAdvanced) ...[
                  const Divider(height: 1),
                  Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextField(
                          controller: _controller,
                          decoration: InputDecoration(
                            labelText: 'Custom Server URL',
                            hintText: SettingsService.defaultBaseUrl,
                            border: const OutlineInputBorder(),
                            prefixIcon: const Icon(Icons.dns),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: _resetToDefault,
                                icon: const Icon(Icons.restore),
                                label: const Text('Reset'),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: ElevatedButton.icon(
                                onPressed: _saveBaseUrl,
                                icon: const Icon(Icons.save),
                                label: const Text('Save'),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),

          const SizedBox(height: 16),

          // WiFi Setup
          Card(
            child: ListTile(
              leading: Icon(
                Icons.wifi_tethering,
                color: theme.colorScheme.secondary,
              ),
              title: const Text('WiFi Setup'),
              subtitle: const Text('Connect the speaker to a WiFi network'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const WifiSetupScreen(),
                  ),
                );
              },
            ),
          ),

          const SizedBox(height: 8),

          // Parental Controls
          Card(
            child: ListTile(
              leading: Icon(
                Icons.family_restroom,
                color: theme.colorScheme.secondary,
              ),
              title: const Text('Parental Controls'),
              subtitle: const Text('Volume limits, quiet hours, chip access'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const ParentalControlsScreen(),
                  ),
                );
              },
            ),
          ),

          const SizedBox(height: 8),

          // Developer Tools
          Card(
            child: ListTile(
              leading: Icon(
                Icons.developer_mode,
                color: theme.colorScheme.secondary,
              ),
              title: const Text('Developer Tools'),
              subtitle: const Text('System info, logs, service controls'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const DeveloperToolsScreen(),
                  ),
                );
              },
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
                    'Default hostname: rpi2\nMake sure your phone is on the same network as the speaker.',
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
