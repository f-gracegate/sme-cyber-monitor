import 'dart:async';
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../core/config.dart';

class ApiException implements Exception {
  ApiException(this.status, this.code, this.message);

  final int status;
  final String code;
  final String message;

  bool get isNetwork => status == 0;

  @override
  String toString() => message;
}

/// Where the session tokens live. On a phone this is the Keychain / Android Keystore.
abstract class TokenStore {
  Future<String?> read(String key);
  Future<void> write(String key, String? value);
}

class SecureTokenStore implements TokenStore {
  // Readable only while the phone is unlocked, and never restored onto another device.
  static const _storage = FlutterSecureStorage(
    iOptions: IOSOptions(accessibility: KeychainAccessibility.unlocked_this_device),
  );

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String? value) =>
      value == null ? _storage.delete(key: key) : _storage.write(key: key, value: value);
}

class MemoryTokenStore implements TokenStore {
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }
}

/// Talks to the SME Cybersecurity Monitoring API with bearer tokens.
///
/// Access tokens last 15 minutes. When one expires, the client rotates the refresh token once
/// and retries; if that fails the person is signed out.
class ApiClient {
  ApiClient({required this.store, String? baseUrl, http.Client? client})
    : baseUrl = baseUrl ?? AppConfig.apiBaseUrl,
      _http = client ?? http.Client();

  static const accessKey = 'access_token';
  static const refreshKey = 'refresh_token';
  static const _timeout = Duration(seconds: 20);

  final TokenStore store;
  final String baseUrl;
  final http.Client _http;
  String? organisationId;
  String? _access;

  /// Called when the session can no longer be refreshed.
  void Function()? onSessionEnded;
  Future<bool>? _refreshing;

  Future<bool> hasSession() async => (await store.read(refreshKey)) != null;

  Future<void> saveTokens(Map<String, dynamic> tokens) async {
    _access = tokens['access_token'] as String;
    await store.write(accessKey, _access);
    await store.write(refreshKey, tokens['refresh_token'] as String);
  }

  Future<void> clearTokens() async {
    _access = null;
    await store.write(accessKey, null);
    await store.write(refreshKey, null);
  }

  Future<dynamic> get(String path, {Map<String, dynamic>? query, bool org = true}) =>
      _send('GET', path, query: query, org: org);

  Future<dynamic> post(String path, {Object? body, bool org = true}) =>
      _send('POST', path, body: body, org: org);

  Future<dynamic> patch(String path, Object? body) => _send('PATCH', path, body: body);

  Future<dynamic> put(String path, Object? body) => _send('PUT', path, body: body);

  Future<dynamic> delete(String path, {bool org = true}) => _send('DELETE', path, org: org);

  Uri _uri(String path, Map<String, dynamic>? query) {
    final base = Uri.parse('$baseUrl/api/v1$path');
    if (query == null || query.isEmpty) return base;
    final params = <String, List<String>>{};
    query.forEach((k, v) {
      if (v == null) return;
      params[k] = v is List ? v.map((e) => '$e').toList() : ['$v'];
    });
    return base.replace(queryParameters: params);
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    bool org = true,
    bool retried = false,
  }) async {
    if (!AppConfig.isAllowedBaseUrl(baseUrl)) {
      throw ApiException(0, 'insecure_server', 'The server address must use HTTPS.');
    }
    _access ??= await store.read(accessKey);
    final request = http.Request(method, _uri(path, query))
      ..headers['accept'] = 'application/json'
      ..headers['user-agent'] = 'SMECM-Mobile/${AppConfig.appVersion}';
    if (_access != null) request.headers['authorization'] = 'Bearer $_access';
    if (org && organisationId != null) request.headers['x-organisation-id'] = organisationId!;
    if (body != null) {
      request.headers['content-type'] = 'application/json';
      request.body = jsonEncode(body);
    }

    http.Response response;
    try {
      response = await http.Response.fromStream(await _http.send(request).timeout(_timeout));
    } on TimeoutException {
      throw ApiException(0, 'timeout', 'The server took too long to answer. Try again.');
    } catch (_) {
      throw ApiException(0, 'network', "Can't reach the server. Check your connection.");
    }

    if (response.statusCode == 401 && !retried && !path.startsWith('/auth/')) {
      final code = _errorCode(response);
      if (code == 'session_expired' || code == 'not_authenticated') {
        if (await _refresh()) {
          return _send(method, path, query: query, body: body, org: org, retried: true);
        }
        await clearTokens();
        onSessionEnded?.call();
      }
    }
    return _decode(response);
  }

  String? _errorCode(http.Response r) {
    try {
      final error = (jsonDecode(r.body) as Map<String, dynamic>)['error'];
      return error is Map ? error['code'] as String? : null;
    } catch (_) {
      return null;
    }
  }

  dynamic _decode(http.Response r) {
    dynamic data;
    if (r.bodyBytes.isNotEmpty) {
      try {
        data = jsonDecode(utf8.decode(r.bodyBytes));
      } catch (_) {
        data = null;
      }
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return data;
    final error = data is Map<String, dynamic> ? data['error'] as Map<String, dynamic>? : null;
    var message = error?['message'] as String? ?? 'Something went wrong (${r.statusCode}).';
    final details = error?['details'];
    if (details is List && details.isNotEmpty && details.first is Map) {
      message = (details.first as Map)['message'] as String? ?? message;
    }
    throw ApiException(r.statusCode, error?['code'] as String? ?? 'error', message);
  }

  /// Refresh at most once at a time, however many requests found an expired token together.
  Future<bool> _refresh() {
    return _refreshing ??= () async {
      try {
        final token = await store.read(refreshKey);
        if (token == null) return false;
        final r = await _http
            .post(
              _uri('/auth/refresh', null),
              headers: {'content-type': 'application/json'},
              body: jsonEncode({'refresh_token': token}),
            )
            .timeout(_timeout);
        if (r.statusCode != 200) return false;
        final tokens = (jsonDecode(r.body) as Map<String, dynamic>)['tokens'];
        if (tokens is! Map<String, dynamic>) return false;
        await saveTokens(tokens);
        return true;
      } catch (_) {
        return false;
      } finally {
        _refreshing = null;
      }
    }();
  }
}
