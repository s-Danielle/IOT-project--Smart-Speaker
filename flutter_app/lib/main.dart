// =============================================================================
// SMART SPEAKER - Flutter Companion App
// =============================================================================
//
// This is the app's entry point. In Flutter, everything starts from main() and
// runApp(). The root widget is typically a MaterialApp (or CupertinoApp for iOS
// style), which sets up navigation, theme, and the first screen ("home").
//
// Project structure:
//   lib/
//     main.dart          <- you are here (entry + root widget)
//     screens/           <- full-screen UIs (home, chips, library, settings, etc.)
//     models/            <- data classes (Chip, Song, Status, ParentalSettings)
//     services/          <- API client, local storage, Spotify helpers
// =============================================================================

import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

/// Application entry point. Flutter calls this once when the app starts.
/// [runApp] attaches the given widget to the screen and starts the frame pipeline.
void main() {
  runApp(const MyApp());
}

/// Root widget of the app. It is a [StatelessWidget]: it has no mutable state,
/// so Flutter only calls [build] when the widget is first inserted or when the
/// parent rebuilds with a new MyApp instance.
///
/// MyApp's job is to create a [MaterialApp], which provides:
/// - [MaterialApp.title]: used by the OS (e.g. task switcher), not shown in UI
/// - [MaterialApp.theme]: default colors, shapes, and text styles for the app
/// - [MaterialApp.home]: the first screen shown when the app opens
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  /// [key] is optional. Passing [super.key] lets Flutter preserve widget identity
  /// when the widget tree is updated. Rarely needed at the root.

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Speaker',

      // -----------------------------------------------------------------------
      // Theme: one place to define colors and component styles app-wide.
      // Child widgets use Theme.of(context) to read these values.
      // -----------------------------------------------------------------------
      theme: ThemeData(
        // Material 3 color scheme derived from a single seed color.
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4), // Purple; generates primary, secondary, etc.
          brightness: Brightness.light,
        ),
        useMaterial3: true,

        // Default look for all Card widgets (elevation = shadow, shape = corners).
        cardTheme: CardThemeData(
          elevation: 2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),

        // Default style for ElevatedButton (padding and rounded corners).
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          ),
        ),

        // App bars: title centered.
        appBarTheme: const AppBarTheme(
          centerTitle: true,
        ),
      ),

      // First screen the user sees. All other screens are pushed on top via Navigator.
      home: const HomeScreen(),
    );
  }
}
