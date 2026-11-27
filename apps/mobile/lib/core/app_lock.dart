import 'package:flutter/widgets.dart';
import 'package:local_auth/local_auth.dart';

import '../api/api_client.dart';

/// Optional Face ID / fingerprint / device-passcode lock, so a borrowed or stolen unlocked
/// phone does not open straight into the organisation's security data.
class AppLock extends ChangeNotifier with WidgetsBindingObserver {
  AppLock(this._prefs, {LocalAuthentication? auth}) : _auth = auth ?? LocalAuthentication();

  static const _key = 'app_lock';
  static const relockAfter = Duration(minutes: 1);

  final TokenStore _prefs;
  final LocalAuthentication _auth;
  bool enabled = false;
  bool locked = false;
  bool supported = false;
  DateTime? _backgroundedAt;

  Future<void> load() async {
    enabled = await _prefs.read(_key) == 'on';
    try {
      supported = await _auth.isDeviceSupported();
    } catch (_) {
      supported = false;
    }
    locked = enabled && supported;
    WidgetsBinding.instance.addObserver(this);
    notifyListeners();
  }

  Future<bool> unlock() async {
    try {
      final ok = await _auth.authenticate(
        localizedReason: 'Unlock SME Cybersecurity Monitoring',
        persistAcrossBackgrounding: true,
      );
      if (ok) {
        locked = false;
        notifyListeners();
      }
      return ok;
    } catch (_) {
      return false;
    }
  }

  /// Turning the lock on asks for authentication first, so it can't be set up by someone who
  /// can't also unlock it.
  Future<bool> setEnabled(bool value) async {
    if (value) {
      if (!supported) return false;
      final ok = await _auth.authenticate(localizedReason: 'Turn on the app lock');
      if (!ok) return false;
    }
    enabled = value;
    await _prefs.write(_key, value ? 'on' : null);
    notifyListeners();
    return true;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!enabled) return;
    if (state == AppLifecycleState.paused || state == AppLifecycleState.hidden) {
      _backgroundedAt ??= DateTime.now();
    } else if (state == AppLifecycleState.resumed) {
      final away = _backgroundedAt;
      _backgroundedAt = null;
      if (away != null && DateTime.now().difference(away) >= relockAfter) {
        locked = true;
        notifyListeners();
      }
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
}
