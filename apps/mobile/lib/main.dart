import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'core/app_lock.dart';
import 'core/config.dart';
import 'core/push.dart';
import 'core/session.dart';
import 'core/ui.dart';
import 'screens/auth.dart';
import 'screens/home.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final store = SecureTokenStore();
  final session = Session(ApiClient(store: store));
  final lock = AppLock(store);
  await Future.wait([session.start(), lock.load()]);
  runApp(SmecmApp(session: session, push: PushService(session), lock: lock));
}

class SmecmApp extends StatelessWidget {
  const SmecmApp({super.key, required this.session, required this.push, required this.lock});

  final Session session;
  final PushService push;
  final AppLock lock;

  @override
  Widget build(BuildContext context) {
    return SessionScope(
      session: session,
      child: MaterialApp(
        title: AppConfig.productName,
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        home: ListenableBuilder(
          listenable: Listenable.merge([session, lock]),
          builder: (context, _) => _route(),
        ),
      ),
    );
  }

  Widget _route() {
    switch (session.status) {
      case SessionStatus.starting:
        return const Scaffold(body: Center(child: CircularProgressIndicator()));
      case SessionStatus.signedOut:
        return SignInScreen(key: const ValueKey('sign-in-screen'), session: session);
      case SessionStatus.ready:
        break;
    }
    if (lock.locked) return LockScreen(lock: lock);
    final me = session.me;
    if (me == null) {
      // Started offline: try again.
      return Scaffold(
        body: ErrorView(
          error: ApiException(0, 'network', "Can't reach the server. Check your connection."),
          onRetry: session.start,
        ),
      );
    }
    if (me.mustChangePassword) return ChangePasswordScreen(session: session);
    final membership = session.membership;
    if (membership == null) return OrganisationPicker(session: session);
    if (membership.requireMfa && !me.mfaEnabled) return MfaRequiredScreen(session: session);
    return HomeShell(
      key: ValueKey('home-${session.orgId}'),
      session: session,
      push: push,
      lock: lock,
    );
  }
}
