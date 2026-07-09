import 'package:flutter/material.dart';

/// Web stand-in for the NFC scan screen. The real implementation
/// ([scan_chip_screen.dart]) depends on dart:io and nfc_manager, which are
/// unavailable on web, so this stub is substituted via a conditional import.
/// It should normally never be shown since the UI hides NFC entry points on
/// web, but it renders a friendly explanation just in case.
class ScanChipScreen extends StatelessWidget {
  const ScanChipScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan Chip'),
        backgroundColor: theme.colorScheme.primary,
        foregroundColor: theme.colorScheme.onPrimary,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.nfc_outlined, size: 80, color: Colors.grey.shade400),
              const SizedBox(height: 24),
              const Text(
                'NFC scanning is not available in the browser',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w500),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                'Use the Android app to scan and register chips. '
                'You can still manage existing chips from the Chips screen.',
                style: TextStyle(color: Colors.grey.shade600),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
