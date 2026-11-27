import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smecm_mobile/api/api_client.dart';
import 'package:smecm_mobile/core/session.dart';
import 'package:smecm_mobile/screens/home.dart';
import 'package:smecm_mobile/screens/incidents.dart';

import 'app_test.dart' show me, tokens;

void main() {
  testWidgets('taking ownership updates the incident without an error', (tester) async {
    Map<String, dynamic>? owner;
    Map<String, dynamic> inc() => {
      'id': 'i1',
      'reference': 'INC-0001',
      'title': 'x',
      'summary': '',
      'severity': 'medium',
      'status': 'open',
      'category': 'phishing',
      'source': 'manual',
      'owner': owner,
      'reporter': {'id': 'u1', 'name': 'Ama'},
      'created_at': DateTime.now().toIso8601String(),
      'updated_at': DateTime.now().toIso8601String(),
      'contained_at': null,
      'resolved_at': null,
      'closed_at': null,
      'closure_reason': null,
      'resolution_summary': null,
      'asset_count': 0,
      'alert_count': 0,
      'open_tasks': 0,
      'assets': [],
      'alerts': [],
      'timeline': [],
      'evidence': [],
      'tasks': [],
      'can_manage': true,
    };
    final client = MockClient((req) async {
      if (req.method == 'PATCH') owner = {'id': 'u1', 'name': 'Ama'};
      if (req.url.path.endsWith('/auth/login')) {
        return http.Response(jsonEncode({'status': 'ok', 'me': me(), 'tokens': tokens}), 200);
      }
      return http.Response(jsonEncode(inc()), 200);
    });
    final session = Session(
      ApiClient(store: MemoryTokenStore(), baseUrl: 'http://localhost:8100', client: client),
    );
    await session.signIn('a', 'b');
    await tester.pumpWidget(
      SessionScope(
        session: session,
        child: MaterialApp(
          home: IncidentDetailScreen(session: session, incidentId: 'i1'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Take ownership'));
    await tester.pumpAndSettle();
    expect(find.text('Something went wrong. Try again.'), findsNothing);
  });
}
