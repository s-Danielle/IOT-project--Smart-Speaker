import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:iot2/main.dart';

void main() {
  testWidgets('App renders home screen', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('Smart Speaker'), findsOneWidget);
    expect(find.text('Connection Status'), findsOneWidget);
    expect(find.text('Chips'), findsOneWidget);
    expect(find.text('Library'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
  });
}
