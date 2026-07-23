import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/settings_service.dart';
// wifi_iot is Android-only; the stub silently returns false on web.
import '../services/wifi_connector_stub.dart'
    if (dart.library.io) '../services/wifi_connector.dart';

const _apIp = '192.168.4.1';
const _apBase = 'http://$_apIp:8080';
const _apSsid = 'SmartSpeaker-Setup';

enum _Step { finding, joinHotspot, pickNetwork, connecting, awaitingHome, success }

class WifiSetupScreen extends StatefulWidget {
  const WifiSetupScreen({super.key});

  @override
  State<WifiSetupScreen> createState() => _WifiSetupScreenState();
}

class _WifiSetupScreenState extends State<WifiSetupScreen> {
  _Step _step = _Step.finding;

  /// Which API base to call during the wizard (AP IP or saved base URL).
  String _wizardBase = _apBase;

  // ── Finding step ──
  String? _findError;

  // ── Join hotspot step ──
  bool _joiningProgrammatic = false;
  String? _joinError;
  Timer? _joinPollTimer;

  // ── Pick network step ──
  bool _scanLoading = false;
  List<Map<String, dynamic>> _networks = [];
  String? _scanError;
  String? _selectedSsid;

  // ── Connecting step ──
  bool _connectLoading = false;
  String? _connectError;
  Timer? _pollTimer;
  int _timeoutPollCount = 0;

  // ── Success step ──
  String? _connectedSsid;

  @override
  void initState() {
    super.initState();
    _startFinding();
  }

  @override
  void dispose() {
    _joinPollTimer?.cancel();
    _pollTimer?.cancel();
    super.dispose();
  }

  // ════════════════════════════════════════════════════════════
  // STEP 1 — FIND SPEAKER
  // ════════════════════════════════════════════════════════════

  Future<void> _startFinding() async {
    setState(() {
      _step = _Step.finding;
      _findError = null;
    });

    // Check configured base URL first
    final savedBase = await SettingsService.getBaseUrl();
    final savedReachable = await ApiService(savedBase).isReachable();
    if (!mounted) return;

    if (savedReachable) {
      _wizardBase = savedBase;
      // Already online — ask the user if they want to change WiFi or exit.
      _showAlreadyOnlineDialog(savedBase);
      return;
    }

    // Check AP IP
    final apReachable = await ApiService(_apBase).isReachable();
    if (!mounted) return;

    if (apReachable) {
      _wizardBase = _apBase;
      _startScan();
      return;
    }

    // Speaker not found anywhere — guide the user to join the AP.
    setState(() => _step = _Step.joinHotspot);
    if (!kIsWeb) {
      _tryProgrammaticJoin();
    } else {
      _startJoinPoll();
    }
  }

  Future<void> _showAlreadyOnlineDialog(String base) async {
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Speaker is online'),
        content: Text('The speaker is reachable at $base.\n\n'
            'Do you still want to change its WiFi network?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Change WiFi'),
          ),
        ],
      ),
    );
    if (!mounted) return;
    if (result == true) {
      _startScan();
    } else {
      Navigator.pop(context);
    }
  }

  // ════════════════════════════════════════════════════════════
  // STEP 2 — JOIN HOTSPOT
  // ════════════════════════════════════════════════════════════

  Future<void> _tryProgrammaticJoin() async {
    setState(() {
      _joiningProgrammatic = true;
      _joinError = null;
    });

    final ok = await WifiConnector.connectToSetupAp(_apSsid);
    if (!mounted) return;

    if (ok) {
      // Give the OS a moment to bind before probing
      await Future.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      final reachable = await ApiService(_apBase).isReachable(timeoutSeconds: 5);
      if (!mounted) return;
      if (reachable) {
        _wizardBase = _apBase;
        setState(() => _joiningProgrammatic = false);
        _startScan();
        return;
      }
    }

    setState(() {
      _joiningProgrammatic = false;
      _joinError = ok
          ? 'Joined the hotspot but the speaker is not responding at $_apIp. '
              'Try joining manually in WiFi settings.'
          : 'Could not join the hotspot automatically. '
              'Please connect manually in WiFi settings.';
    });
    _startJoinPoll();
  }

  void _startJoinPoll() {
    _joinPollTimer?.cancel();
    _joinPollTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      final reachable = await ApiService(_apBase).isReachable(timeoutSeconds: 3);
      if (!mounted) return;
      if (reachable) {
        _joinPollTimer?.cancel();
        _wizardBase = _apBase;
        _startScan();
      }
    });
  }

  // ════════════════════════════════════════════════════════════
  // STEP 3 — PICK NETWORK
  // ════════════════════════════════════════════════════════════

  Future<void> _startScan() async {
    setState(() {
      _step = _Step.pickNetwork;
      _scanLoading = true;
      _scanError = null;
      _networks = [];
      _selectedSsid = null;
    });

    try {
      final result = await ApiService(_wizardBase).scanWifiNetworks();
      if (!mounted) return;
      final raw = result['networks'];
      final networks = raw is List
          ? raw.map((e) => Map<String, dynamic>.from(e as Map)).toList()
          : <Map<String, dynamic>>[];
      setState(() {
        _networks = networks;
        _scanLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _scanError = e.toString();
        _scanLoading = false;
      });
    }
  }

  Future<void> _selectNetwork(String ssid, bool isOpen) async {
    if (isOpen) {
      _connectToNetwork(ssid, null);
      return;
    }

    final password = await showDialog<String>(
      context: context,
      builder: (ctx) => _PasswordDialog(ssid: ssid),
    );
    if (!mounted) return;
    if (password != null) _connectToNetwork(ssid, password.isEmpty ? null : password);
  }

  Future<void> _showHiddenNetworkDialog() async {
    final result = await showDialog<_NetworkInput>(
      context: context,
      builder: (ctx) => const _HiddenNetworkDialog(),
    );
    if (!mounted || result == null) return;
    _connectToNetwork(result.ssid, result.password.isEmpty ? null : result.password);
  }

  // ════════════════════════════════════════════════════════════
  // STEP 4 — CONNECT & CONFIRM
  // ════════════════════════════════════════════════════════════

  Future<void> _connectToNetwork(String ssid, String? password) async {
    setState(() {
      _step = _Step.connecting;
      _selectedSsid = ssid;
      _connectLoading = true;
      _connectError = null;
      _timeoutPollCount = 0;
    });

    try {
      await ApiService(_wizardBase).connectWifi(ssid, password: password);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _connectError = 'Failed to send connect request: $e';
        _connectLoading = false;
      });
      return;
    }

    if (!mounted) return;
    _startStatusPoll(ssid);
  }

  void _startStatusPoll(String ssid) {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      try {
        final status = await ApiService(_wizardBase).getWifiConnectStatus();
        if (!mounted) return;
        final state = status['state'] as String? ?? 'idle';

        if (state == 'connected') {
          _pollTimer?.cancel();
          await WifiConnector.releaseWifiBinding();
          setState(() {
            _connectedSsid = ssid;
            _step = _Step.success;
            _connectLoading = false;
          });
        } else if (state == 'failed') {
          _pollTimer?.cancel();
          setState(() {
            _connectError = status['error'] as String? ?? 'Connection failed';
            _connectLoading = false;
          });
        }
        // state == 'connecting' or 'idle' → keep polling
      } catch (_) {
        if (!mounted) return;
        _timeoutPollCount++;
        // ~5 consecutive failures mean the AP was torn down (likely success)
        if (_timeoutPollCount >= 5) {
          _pollTimer?.cancel();
          await WifiConnector.releaseWifiBinding();
          if (!mounted) return;
          setState(() {
            _step = _Step.awaitingHome;
            _connectedSsid = ssid;
            _connectLoading = false;
          });
          _startHomeProbe();
        }
      }
    });
  }

  // ════════════════════════════════════════════════════════════
  // AWAITING HOME — speaker joining home network
  // ════════════════════════════════════════════════════════════

  void _startHomeProbe() {
    final homeUrls = [
      'http://rpi2.local:8080',
      if (_wizardBase != _apBase) _wizardBase,
    ];

    Timer.periodic(const Duration(seconds: 3), (t) async {
      for (final url in homeUrls) {
        final reachable = await ApiService(url).isReachable(timeoutSeconds: 3);
        if (!mounted) {
          t.cancel();
          return;
        }
        if (reachable) {
          t.cancel();
          setState(() => _step = _Step.success);
          return;
        }
      }
    });
  }

  // ════════════════════════════════════════════════════════════
  // BUILD
  // ════════════════════════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('WiFi Setup'),
        backgroundColor: theme.colorScheme.primary,
        foregroundColor: theme.colorScheme.onPrimary,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: switch (_step) {
            _Step.finding => _buildFinding(theme),
            _Step.joinHotspot => _buildJoinHotspot(theme),
            _Step.pickNetwork => _buildPickNetwork(theme),
            _Step.connecting => _buildConnecting(theme),
            _Step.awaitingHome => _buildAwaitingHome(theme),
            _Step.success => _buildSuccess(theme),
          },
        ),
      ),
    );
  }

  // ── Step indicator ────────────────────────────────────────────

  Widget _stepIndicator(int current) {
    final labels = ['Find', 'Join', 'Network', 'Connect'];
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(labels.length, (i) {
        final active = i < current;
        final isCurrent = i == current - 1;
        return Row(
          children: [
            CircleAvatar(
              radius: 14,
              backgroundColor: active || isCurrent ? Colors.blue : Colors.grey.shade300,
              child: Text(
                '${i + 1}',
                style: TextStyle(
                  color: active || isCurrent ? Colors.white : Colors.grey.shade600,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            if (i < labels.length - 1)
              Container(
                width: 32,
                height: 2,
                color: active ? Colors.blue : Colors.grey.shade300,
              ),
          ],
        );
      }),
    );
  }

  // ── Finding ──────────────────────────────────────────────────

  Widget _buildFinding(ThemeData theme) {
    return Column(
      children: [
        _stepIndicator(1),
        const SizedBox(height: 32),
        const CircularProgressIndicator(),
        const SizedBox(height: 24),
        const Text(
          'Looking for your speaker…',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w500),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 8),
        Text(
          'Checking both your local network and the setup hotspot.',
          style: TextStyle(color: Colors.grey.shade600),
          textAlign: TextAlign.center,
        ),
        if (_findError != null) ...[
          const SizedBox(height: 24),
          _errorCard(_findError!),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: _startFinding,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
          ),
        ],
      ],
    );
  }

  // ── Join hotspot ──────────────────────────────────────────────

  Widget _buildJoinHotspot(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _stepIndicator(2),
        const SizedBox(height: 24),
        _gradientCard(
          theme,
          Colors.blue,
          Icons.wifi,
          'Connect to the Speaker Hotspot',
          'The speaker creates a setup network when it has no WiFi.',
        ),
        const SizedBox(height: 24),
        if (_joiningProgrammatic) ...[
          const Center(child: CircularProgressIndicator()),
          const SizedBox(height: 16),
          const Text(
            'Connecting to SmartSpeaker-Setup…',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 15),
          ),
        ] else ...[
          if (_joinError != null) ...[
            _errorCard(_joinError!),
            const SizedBox(height: 16),
          ],
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Manual setup',
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  _step2Item('1', 'Open your device\'s WiFi settings'),
                  _step2Item('2', 'Connect to "SmartSpeaker-Setup"'),
                  _step2Item('3', 'Return here — this page will auto-advance'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _startJoinPoll,
                  icon: const Icon(Icons.refresh),
                  label: const Text('I\'m connected'),
                ),
              ),
              if (!kIsWeb) ...[
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _tryProgrammaticJoin,
                    icon: const Icon(Icons.wifi_find),
                    label: const Text('Try auto-join'),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 16),
          Center(
            child: TextButton.icon(
              onPressed: _startScan,
              icon: const Icon(Icons.skip_next),
              label: const Text('Skip (already on hotspot)'),
            ),
          ),
        ],
      ],
    );
  }

  Widget _step2Item(String num, String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: 12,
            backgroundColor: Colors.blue.shade100,
            child: Text(num,
                style:
                    TextStyle(color: Colors.blue.shade700, fontSize: 11)),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }

  // ── Pick network ──────────────────────────────────────────────

  Widget _buildPickNetwork(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _stepIndicator(3),
        const SizedBox(height: 20),
        Row(
          children: [
            Expanded(
              child: Text(
                'Choose a network',
                style: theme.textTheme.titleLarge
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
            ),
            IconButton(
              onPressed: _scanLoading ? null : _startScan,
              icon: _scanLoading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.refresh),
              tooltip: 'Refresh',
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (_scanLoading)
          const Center(
              child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator()))
        else if (_scanError != null) ...[
          _errorCard(_scanError!),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: _startScan,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
          ),
        ] else ...[
          if (_networks.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 32),
              child: Center(
                child: Text('No networks found.',
                    style: TextStyle(color: Colors.grey.shade600)),
              ),
            )
          else
            ...(_networks.map((n) => _networkTile(n, theme))),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _showHiddenNetworkDialog,
            icon: const Icon(Icons.add),
            label: const Text('Hidden network…'),
          ),
        ],
      ],
    );
  }

  Widget _networkTile(Map<String, dynamic> n, ThemeData theme) {
    final ssid = n['ssid'] as String? ?? '';
    final signal = n['signal'] as int? ?? 0;
    final security = (n['security'] as String? ?? '').trim();
    final isOpen = security.isEmpty || security == '--' || security == 'Open';
    final bars = _signalIcon(signal);

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: Icon(bars, color: theme.colorScheme.primary),
        title: Text(ssid, style: const TextStyle(fontWeight: FontWeight.w500)),
        subtitle: Text(isOpen ? 'Open' : security,
            style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
        trailing: isOpen
            ? null
            : const Icon(Icons.lock_outline, size: 18),
        onTap: () => _selectNetwork(ssid, isOpen),
      ),
    );
  }

  IconData _signalIcon(int signal) {
    if (signal >= 75) return Icons.signal_wifi_4_bar;
    if (signal >= 50) return Icons.network_wifi_3_bar;
    if (signal >= 25) return Icons.network_wifi_2_bar;
    return Icons.network_wifi_1_bar;
  }

  // ── Connecting ───────────────────────────────────────────────

  Widget _buildConnecting(ThemeData theme) {
    return Column(
      children: [
        _stepIndicator(4),
        const SizedBox(height: 32),
        if (_connectLoading) ...[
          const CircularProgressIndicator(),
          const SizedBox(height: 24),
          Text(
            'Connecting to "$_selectedSsid"…',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w500),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            'The speaker is switching networks. '
            'This may take up to 30 seconds.',
            style: TextStyle(color: Colors.grey.shade600),
            textAlign: TextAlign.center,
          ),
        ] else if (_connectError != null) ...[
          const Icon(Icons.error_outline, size: 64, color: Colors.red),
          const SizedBox(height: 16),
          const Text('Connection failed',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          _errorCard(_connectError!),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _startScan,
            icon: const Icon(Icons.arrow_back),
            label: const Text('Try another network'),
          ),
        ],
      ],
    );
  }

  // ── Awaiting home ─────────────────────────────────────────────

  Widget _buildAwaitingHome(ThemeData theme) {
    return Column(
      children: [
        const SizedBox(height: 32),
        _gradientCard(
          theme,
          Colors.orange,
          Icons.swap_horiz,
          'Speaker is switching networks',
          'The speaker has left the setup hotspot and is joining "$_connectedSsid".',
        ),
        const SizedBox(height: 32),
        const CircularProgressIndicator(),
        const SizedBox(height: 24),
        Text(
          'Waiting for the speaker to appear on your network…',
          style: TextStyle(color: Colors.grey.shade700),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 32),
        Card(
          color: Colors.blue.shade50,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  children: [
                    Icon(Icons.info_outline, color: Colors.blue.shade700),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'Reconnect your phone to your home WiFi if needed',
                        style: TextStyle(fontWeight: FontWeight.w500),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Once reconnected, this page will detect your speaker automatically.',
                  style: TextStyle(color: Colors.grey.shade700, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ── Success ───────────────────────────────────────────────────

  Widget _buildSuccess(ThemeData theme) {
    return Column(
      children: [
        const SizedBox(height: 32),
        Container(
          width: 100,
          height: 100,
          decoration: BoxDecoration(
            color: Colors.green.shade100,
            shape: BoxShape.circle,
          ),
          child: Icon(Icons.check_circle,
              size: 64, color: Colors.green.shade600),
        ),
        const SizedBox(height: 24),
        const Text(
          'Speaker connected!',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
        if (_connectedSsid != null) ...[
          const SizedBox(height: 8),
          Text(
            'Connected to "$_connectedSsid"',
            style: TextStyle(color: Colors.grey.shade700),
          ),
        ],
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.grey.shade100,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            children: [
              Icon(Icons.language, color: theme.colorScheme.primary),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Reach your speaker from any browser at:\nhttp://rpi2.local:8080',
                  style: TextStyle(fontFamily: 'monospace', fontSize: 13),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 32),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.home),
            label: const Text('Done', style: TextStyle(fontSize: 16)),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.green,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ),
      ],
    );
  }

  // ── Helpers ───────────────────────────────────────────────────

  Widget _errorCard(String message) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.red.shade200),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline, color: Colors.red.shade600, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: Colors.red.shade800, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  Widget _gradientCard(
    ThemeData theme,
    Color color,
    IconData icon,
    String title,
    String subtitle,
  ) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [color.withValues(alpha: 0.8), color],
          ),
        ),
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: Colors.white, size: 28),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(subtitle,
                      style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.9),
                          fontSize: 13)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════
// PASSWORD DIALOG
// ════════════════════════════════════════════════════════════════

class _PasswordDialog extends StatefulWidget {
  final String ssid;
  const _PasswordDialog({required this.ssid});

  @override
  State<_PasswordDialog> createState() => _PasswordDialogState();
}

class _PasswordDialogState extends State<_PasswordDialog> {
  final _controller = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Connect to "${widget.ssid}"'),
      content: TextField(
        controller: _controller,
        obscureText: _obscure,
        autofocus: true,
        decoration: InputDecoration(
          labelText: 'WiFi Password',
          border: const OutlineInputBorder(),
          suffixIcon: IconButton(
            icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
            onPressed: () => setState(() => _obscure = !_obscure),
          ),
        ),
        onSubmitted: (_) => Navigator.pop(context, _controller.text),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: () => Navigator.pop(context, _controller.text),
          child: const Text('Connect'),
        ),
      ],
    );
  }
}

// ════════════════════════════════════════════════════════════════
// HIDDEN NETWORK DIALOG
// ════════════════════════════════════════════════════════════════

class _NetworkInput {
  final String ssid;
  final String password;
  _NetworkInput(this.ssid, this.password);
}

class _HiddenNetworkDialog extends StatefulWidget {
  const _HiddenNetworkDialog();

  @override
  State<_HiddenNetworkDialog> createState() => _HiddenNetworkDialogState();
}

class _HiddenNetworkDialogState extends State<_HiddenNetworkDialog> {
  final _ssidController = TextEditingController();
  final _pwController = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _ssidController.dispose();
    _pwController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Hidden Network'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _ssidController,
            decoration: const InputDecoration(
              labelText: 'Network Name (SSID)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pwController,
            obscureText: _obscure,
            decoration: InputDecoration(
              labelText: 'Password (leave empty for open)',
              border: const OutlineInputBorder(),
              suffixIcon: IconButton(
                icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: () {
            if (_ssidController.text.isNotEmpty) {
              Navigator.pop(
                  context, _NetworkInput(_ssidController.text, _pwController.text));
            }
          },
          child: const Text('Connect'),
        ),
      ],
    );
  }
}
