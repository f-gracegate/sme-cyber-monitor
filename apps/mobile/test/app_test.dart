import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smecm_mobile/api/api_client.dart';
import 'package:smecm_mobile/core/app_lock.dart';
import 'package:smecm_mobile/core/config.dart';
import 'package:smecm_mobile/core/push.dart';
import 'package:smecm_mobile/core/session.dart';
import 'package:smecm_mobile/main.dart';

const orgId = '11111111-1111-1111-1111-111111111111';

Map<String, dynamic> me({bool mustChange = false, List<String>? perms}) => {
  'user': {
    'id': 'u1',
    'email': 'ama@example.com',
    'full_name': 'Ama Owner',
    'must_change_password': mustChange,
    'mfa_enabled': false,
  },
  'memberships': [
    {
      'organisation_id': orgId,
      'organisation_name': 'Acme Ltd',
      'role_label': 'Organisation Owner',
      'permissions':
          perms ??
          [
            'org:read',
            'alerts:read',
            'alerts:manage',
            'incidents:read',
            'incidents:manage',
            'incidents:report',
            'remediation:read',
            'remediation:manage',
          ],
      'require_mfa': false,
    },
  ],
};

const tokens = {
  'access_token': 'access-1',
  'refresh_token': 'refresh-1',
  'token_type': 'bearer',
  'expires_in': 900,
};

final overview = {
  'organisation_name': 'Acme Ltd',
  'posture_score': 82,
  'posture_note': 'Based on 3 of 3 monitorable assets reporting',
  'posture_confidence': 100,
  'alerts_open_by_severity': {'critical': 1, 'high': 2, 'medium': 0, 'low': 0},
  'findings_open_by_severity': {'critical': 1, 'high': 2, 'medium': 0, 'low': 0},
  'open_incidents': 1,
  'overdue_tasks': 0,
  'monitored_assets': 3,
  'monitorable_assets': 3,
  'recent_alerts': [
    {
      'id': 'a1',
      'title': 'TLS certificate has expired',
      'severity': 'critical',
      'status': 'new',
      'asset_name': 'Shop',
      'last_seen_at': DateTime.now().toIso8601String(),
    },
  ],
};

http.Response json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

http.Response error(int status, String code, String message) => json({
  'error': {'code': code, 'message': message},
}, status);

void main() {
  test('only HTTPS, or HTTP to the developer machine, is allowed', () {
    expect(AppConfig.isAllowedBaseUrl('https://api.example.com'), isTrue);
    expect(AppConfig.isAllowedBaseUrl('http://localhost:8100'), isTrue);
    expect(AppConfig.isAllowedBaseUrl('http://10.0.2.2:8100'), isTrue);
    expect(AppConfig.isAllowedBaseUrl('http://api.example.com'), isFalse);
  });

  test('an expired access token is refreshed once and the request retried', () async {
    final store = MemoryTokenStore()
      ..values[ApiClient.accessKey] = 'old'
      ..values[ApiClient.refreshKey] = 'refresh-0';
    var refreshes = 0;
    final client = MockClient((req) async {
      if (req.url.path.endsWith('/auth/refresh')) {
        refreshes++;
        expect(jsonDecode(req.body)['refresh_token'], 'refresh-0');
        return json({'message': 'refreshed', 'tokens': tokens});
      }
      if (req.headers['authorization'] == 'Bearer old') {
        return error(401, 'session_expired', 'Please sign in again.');
      }
      expect(req.headers['authorization'], 'Bearer access-1');
      expect(req.headers['x-organisation-id'], orgId);
      return json({'ok': true});
    });
    final api = ApiClient(store: store, baseUrl: 'http://localhost:8100', client: client)
      ..organisationId = orgId;
    expect(await api.get('/overview'), {'ok': true});
    expect(refreshes, 1);
    expect(store.values[ApiClient.refreshKey], 'refresh-1');
  });

  test('the session ends when the refresh token is rejected', () async {
    final store = MemoryTokenStore()
      ..values[ApiClient.accessKey] = 'old'
      ..values[ApiClient.refreshKey] = 'stolen';
    final client = MockClient((req) async {
      if (req.url.path.endsWith('/auth/refresh')) {
        return error(401, 'session_expired', 'Please sign in again.');
      }
      return error(401, 'session_expired', 'Please sign in again.');
    });
    final session = Session(
      ApiClient(store: store, baseUrl: 'http://localhost:8100', client: client),
    )..status = SessionStatus.ready;
    await expectLater(session.api.get('/overview'), throwsA(isA<ApiException>()));
    expect(session.status, SessionStatus.signedOut);
    expect(session.endedMessage, isNotNull);
    expect(store.values, isEmpty);
  });

  testWidgets('sign in, land on the overview, open an alert', (tester) async {
    tester.view.physicalSize = const Size(430, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final requests = <String>[];
    final client = MockClient((req) async {
      requests.add('${req.method} ${req.url.path}');
      switch (req.url.path) {
        case '/api/v1/auth/login':
          final body = jsonDecode(req.body);
          expect(body['client'], 'mobile');
          if (body['password'] != 'right-password') {
            return error(401, 'invalid_credentials', 'Incorrect email/username or password.');
          }
          return json({'status': 'ok', 'me': me(), 'tokens': tokens});
        case '/api/v1/overview':
          return json(overview);
        case '/api/v1/alerts/a1':
          return json({
            'id': 'a1',
            'finding_id': 'f1',
            'asset_id': 's1',
            'title': 'TLS certificate has expired',
            'severity': 'critical',
            'status': 'new',
            'occurrences': 1,
            'first_seen_at': DateTime.now().toIso8601String(),
            'last_seen_at': DateTime.now().toIso8601String(),
            'acknowledged_at': null,
            'resolved_at': null,
            'resolution_note': null,
            'asset': {
              'id': 's1',
              'name': 'Shop',
              'identifier': 'shop.example.com',
              'type': 'website',
              'criticality': 'high',
            },
            'finding': {
              'description': 'The certificate expired yesterday.',
              'impact': 'Visitors see a security warning.',
              'recommendation': 'Renew the certificate.',
            },
            'incident': null,
          });
      }
      return json({'items': [], 'total': 0, 'page': 1, 'page_size': 50, 'unread': 0});
    });
    final store = MemoryTokenStore();
    final session = Session(
      ApiClient(store: store, baseUrl: 'http://localhost:8100', client: client),
    );
    await session.start();
    expect(session.status, SessionStatus.signedOut);

    await tester.pumpWidget(
      SmecmApp(session: session, push: PushService(session), lock: AppLock(store)),
    );
    expect(find.text('Sign in'), findsWidgets);

    await tester.enterText(find.byKey(const Key('identifier')), 'ama@example.com');
    await tester.enterText(find.byKey(const Key('password')), 'wrong');
    await tester.tap(find.byKey(const Key('sign-in')));
    await tester.pumpAndSettle();
    expect(find.text('Incorrect email/username or password.'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('password')), 'right-password');
    await tester.tap(find.byKey(const Key('sign-in')));
    await tester.pumpAndSettle();

    expect(store.values[ApiClient.refreshKey], 'refresh-1');
    expect(find.text('Acme Ltd'), findsOneWidget);
    expect(find.text('82'), findsOneWidget);
    expect(find.text('Open alerts'), findsOneWidget);
    expect(find.text('Report incident'), findsOneWidget);

    await tester.tap(find.text('TLS certificate has expired'));
    await tester.pumpAndSettle();
    expect(find.text('Visitors see a security warning.'), findsOneWidget);
    expect(find.text('Resolve'), findsOneWidget);
    expect(requests, contains('GET /api/v1/alerts/a1'));
  });

  testWidgets('a temporary password must be changed first', (tester) async {
    final client = MockClient(
      (req) async => json({'status': 'ok', 'me': me(mustChange: true), 'tokens': tokens}),
    );
    final store = MemoryTokenStore();
    final session = Session(
      ApiClient(store: store, baseUrl: 'http://localhost:8100', client: client),
    );
    await session.signIn('Admin', 'password');
    await tester.pumpWidget(
      SmecmApp(session: session, push: PushService(session), lock: AppLock(store)),
    );
    expect(find.text('Choose a new password'), findsOneWidget);
  });

  testWidgets('staff without alert access see no Alerts tab', (tester) async {
    final store = MemoryTokenStore()..values[ApiClient.refreshKey] = 'r';
    final client = MockClient((req) async {
      if (req.url.path.endsWith('/auth/me')) {
        return json(me(perms: ['org:read', 'incidents:report']));
      }
      if (req.url.path.endsWith('/overview')) return json(overview);
      return json({'items': [], 'total': 0, 'page': 1, 'page_size': 50});
    });
    final staff = Session(
      ApiClient(store: store, baseUrl: 'http://localhost:8100', client: client),
    );
    await staff.start();
    await tester.pumpWidget(
      SmecmApp(session: staff, push: PushService(staff), lock: AppLock(store)),
    );
    await tester.pumpAndSettle();
    expect(find.widgetWithText(NavigationDestination, 'Alerts'), findsNothing);
    expect(find.widgetWithText(NavigationDestination, 'Incidents'), findsOneWidget);
    expect(find.text('My reports'), findsNothing); // incidents tab not opened yet
  });
}
