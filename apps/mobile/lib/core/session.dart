import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../api/models.dart';

enum SessionStatus { starting, signedOut, ready }

sealed class SignInResult {}

class SignedIn extends SignInResult {}

class NeedsMfa extends SignInResult {
  NeedsMfa(this.mfaToken);
  final String mfaToken;
}

/// Who is signed in, and which organisation they are working in.
class Session extends ChangeNotifier {
  Session(this.api, {TokenStore? prefs}) : _prefs = prefs ?? api.store {
    api.onSessionEnded = _ended;
  }

  static const _orgKey = 'organisation_id';

  final ApiClient api;
  final TokenStore _prefs;
  SessionStatus status = SessionStatus.starting;
  Me? me;
  String? orgId;

  /// A push notification's link waiting for the home screen to open it.
  String? pendingLink;
  String? endedMessage;

  Membership? get membership {
    for (final m in me?.memberships ?? const <Membership>[]) {
      if (m.organisationId == orgId) return m;
    }
    return null;
  }

  bool can(String permission) => membership?.permissions.contains(permission) ?? false;

  Future<void> start() async {
    if (!await api.hasSession()) {
      _setSignedOut();
      return;
    }
    try {
      await _loadMe();
    } on ApiException catch (e) {
      if (e.isNetwork) {
        // Offline at launch: keep the session and let screens show their own retry.
        status = SessionStatus.ready;
        notifyListeners();
        return;
      }
      await api.clearTokens();
      _setSignedOut();
    }
  }

  Future<SignInResult> signIn(String identifier, String password) async {
    final r = await api.post(
      '/auth/login',
      body: {'identifier': identifier.trim(), 'password': password, 'client': 'mobile'},
      org: false,
    ) as Json;
    if (r['status'] == 'mfa_required') return NeedsMfa(r['mfa_token'] as String);
    await _accept(r);
    return SignedIn();
  }

  Future<void> verifyMfa(String mfaToken, String code) async {
    final r = await api.post(
      '/auth/mfa/verify',
      body: {'mfa_token': mfaToken, 'code': code.replaceAll(' ', ''), 'client': 'mobile'},
      org: false,
    ) as Json;
    await _accept(r);
  }

  Future<void> _accept(Json r) async {
    await api.saveTokens(r['tokens'] as Json);
    endedMessage = null;
    _applyMe(Me(r['me'] as Json));
  }

  Future<void> _loadMe() async {
    _applyMe(Me(await api.get('/auth/me', org: false) as Json));
  }

  Future<void> refreshMe() => _loadMe();

  void _applyMe(Me value) {
    me = value;
    final ids = value.memberships.map((m) => m.organisationId).toList();
    if (orgId == null || !ids.contains(orgId)) {
      orgId = ids.length == 1 ? ids.first : null;
    }
    api.organisationId = orgId;
    status = SessionStatus.ready;
    notifyListeners();
    _restoreOrg(ids);
  }

  Future<void> _restoreOrg(List<String> ids) async {
    if (orgId != null) return;
    final saved = await _prefs.read(_orgKey);
    if (saved != null && ids.contains(saved)) selectOrganisation(saved);
  }

  void selectOrganisation(String id) {
    orgId = id;
    api.organisationId = id;
    _prefs.write(_orgKey, id);
    notifyListeners();
  }

  Future<void> changePassword(String current, String next) async {
    await api.post(
      '/auth/password/change',
      body: {'current_password': current, 'new_password': next},
      org: false,
    );
    await _loadMe();
  }

  Future<void> signOut() async {
    try {
      await api.post('/auth/logout', org: false);
    } catch (_) {
      // Signing out locally matters more than telling the server.
    }
    await api.clearTokens();
    _setSignedOut();
  }

  void openLink(String link) {
    pendingLink = link;
    notifyListeners();
  }

  String? takePendingLink() {
    final link = pendingLink;
    pendingLink = null;
    return link;
  }

  void _ended() {
    endedMessage = 'Your session ended. Please sign in again.';
    _setSignedOut();
  }

  void _setSignedOut() {
    me = null;
    orgId = null;
    api.organisationId = null;
    status = SessionStatus.signedOut;
    notifyListeners();
  }
}
