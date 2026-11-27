import 'package:flutter/foundation.dart';

/// Build-time configuration. Pass values with --dart-define, for example:
///
///   flutter run --dart-define=API_BASE_URL=https://api.example.com
class AppConfig {
  AppConfig._();

  static const productName = 'SME Cybersecurity Monitoring';
  static const companyName = 'GraceGate Technologies';
  static const appVersion = '1.0.0';

  /// The API server. The iOS simulator reaches the host machine on localhost; the Android
  /// emulator reaches it on 10.0.2.2.
  static String get apiBaseUrl {
    const configured = String.fromEnvironment('API_BASE_URL');
    if (configured.isNotEmpty) return configured;
    if (defaultTargetPlatform == TargetPlatform.android) return 'http://10.0.2.2:8100';
    return 'http://localhost:8100';
  }

  /// Plain HTTP is only allowed to a developer's own machine. Builds talking to a real server
  /// must use HTTPS, so tokens never cross the network unencrypted.
  static bool isAllowedBaseUrl(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null) return false;
    if (uri.scheme == 'https') return true;
    const local = {'localhost', '127.0.0.1', '10.0.2.2'};
    return uri.scheme == 'http' && local.contains(uri.host);
  }
}
