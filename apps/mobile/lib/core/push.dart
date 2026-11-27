import 'dart:async';
import 'dart:io' show Platform;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import 'config.dart';
import 'session.dart';

enum PushState { notConfigured, denied, enabled, error }

/// Firebase Cloud Messaging: Android directly, iOS through APNs.
///
/// Firebase settings come from --dart-define (FIREBASE_API_KEY, FIREBASE_APP_ID,
/// FIREBASE_SENDER_ID, FIREBASE_PROJECT_ID). Without them the app works normally and push is
/// simply reported as not set up.
class PushService extends ChangeNotifier {
  PushService(this.session);

  final Session session;
  PushState state = PushState.notConfigured;
  String? lastError;
  StreamSubscription<String>? _refreshSub;
  bool _initialised = false;

  /// Shown when a push arrives while the app is open.
  final foreground = StreamController<RemoteMessage>.broadcast();

  static FirebaseOptions? get _options {
    const apiKey = String.fromEnvironment('FIREBASE_API_KEY');
    const appId = String.fromEnvironment('FIREBASE_APP_ID');
    const senderId = String.fromEnvironment('FIREBASE_SENDER_ID');
    const projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
    if (apiKey.isEmpty || appId.isEmpty || senderId.isEmpty || projectId.isEmpty) return null;
    return const FirebaseOptions(
      apiKey: apiKey,
      appId: appId,
      messagingSenderId: senderId,
      projectId: projectId,
      iosBundleId: 'com.gracegate.smecm.smecmMobile',
    );
  }

  bool get configured => _options != null;

  /// Ask permission, register this phone with the API and route taps on notifications.
  Future<void> enable() async {
    final options = _options;
    if (options == null) {
      state = PushState.notConfigured;
      notifyListeners();
      return;
    }
    try {
      if (!_initialised) {
        await Firebase.initializeApp(options: options);
        FirebaseMessaging.onMessage.listen(foreground.add);
        FirebaseMessaging.onMessageOpenedApp.listen(_open);
        final initial = await FirebaseMessaging.instance.getInitialMessage();
        if (initial != null) _open(initial);
        _initialised = true;
      }
      final settings = await FirebaseMessaging.instance.requestPermission();
      if (settings.authorizationStatus == AuthorizationStatus.denied) {
        state = PushState.denied;
        notifyListeners();
        return;
      }
      // Registration tokens are what the FCM HTTP v1 send API targets. Newer SDKs also offer
      // installation IDs (register()/onRegistered); switch once the server sends to those.
      // ignore: deprecated_member_use
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null) await _register(token);
      // ignore: deprecated_member_use
      _refreshSub ??= FirebaseMessaging.instance.onTokenRefresh.listen(_register);
      state = PushState.enabled;
      lastError = null;
    } catch (e) {
      state = PushState.error;
      lastError = e.toString();
    }
    notifyListeners();
  }

  Future<void> _register(String token) async {
    try {
      await session.api.post(
        '/me/push-devices',
        body: {
          'platform': Platform.isIOS ? 'ios' : 'android',
          'token': token,
          'device_name': Platform.isIOS ? 'iPhone' : 'Android phone',
          'app_version': AppConfig.appVersion,
        },
        org: false,
      );
    } on ApiException catch (e) {
      lastError = e.message;
    }
  }

  void _open(RemoteMessage message) {
    final link = message.data['link'] as String?;
    final org = message.data['organisation_id'] as String?;
    if (org != null && org != session.orgId) {
      final belongs = session.me?.memberships.any((m) => m.organisationId == org) ?? false;
      if (belongs) session.selectOrganisation(org);
    }
    if (link != null && link.isNotEmpty) session.openLink(link);
  }

  @override
  void dispose() {
    _refreshSub?.cancel();
    foreground.close();
    super.dispose();
  }
}
