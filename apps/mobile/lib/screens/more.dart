import 'package:flutter/material.dart';

import '../api/models.dart';
import '../core/app_lock.dart';
import '../core/config.dart';
import '../core/push.dart';
import '../core/session.dart';
import '../core/ui.dart';
import 'home.dart';

const _levels = {
  'critical': 'Critical only',
  'high': 'High and critical',
  'medium': 'Medium and above',
  'low': 'Everything',
  'off': 'Off',
};

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key, required this.session, required this.push, required this.lock});

  final Session session;
  final PushService push;
  final AppLock lock;

  @override
  Widget build(BuildContext context) {
    final me = session.me;
    final membership = session.membership;
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        children: [
          ListTile(
            leading: CircleAvatar(child: Text(_initials(me?.fullName ?? '?'))),
            title: Text(me?.fullName ?? ''),
            subtitle: Text(me?.email ?? ''),
          ),
          ListTile(
            leading: const Icon(Icons.business_outlined),
            title: Text(membership?.organisationName ?? ''),
            subtitle: Text(membership?.roleLabel ?? ''),
            trailing: (me?.memberships.length ?? 0) > 1 ? const Text('Switch') : null,
            onTap: (me?.memberships.length ?? 0) > 1 ? () => _switchOrg(context) : null,
          ),
          ListTile(
            leading: const Icon(Icons.inbox_outlined),
            title: const Text('Notifications'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () =>
                Navigator.of(context)
                    .push(MaterialPageRoute(builder: (_) => NotificationsScreen(session: session))),
          ),
          const Divider(),
          _Header('Alerts on this phone'),
          ListenableBuilder(
            listenable: push,
            builder: (context, _) => ListTile(
              leading: Icon(
                push.state == PushState.enabled
                    ? Icons.notifications_active_outlined
                    : Icons.notifications_off_outlined,
              ),
              title: Text(switch (push.state) {
                PushState.enabled => 'Push notifications are on',
                PushState.denied => 'Notifications are blocked',
                PushState.notConfigured => 'Push is not set up in this build',
                PushState.error => "Couldn't turn on notifications",
              }),
              subtitle: Text(switch (push.state) {
                PushState.enabled => 'Urgent alerts arrive even when the app is closed.',
                PushState.denied => 'Allow notifications for this app in your phone settings.',
                PushState.notConfigured => 'Ask your administrator for the full app build.',
                PushState.error => push.lastError ?? 'Try again later.',
              }),
              trailing: push.state == PushState.enabled
                  ? TextButton(onPressed: () => _testPush(context), child: const Text('Test'))
                  : null,
            ),
          ),
          if (session.can('alerts:read') || session.can('incidents:manage'))
            _PushLevel(session: session),
          const Divider(),
          _Header('Security'),
          ListenableBuilder(
            listenable: lock,
            builder: (context, _) => SwitchListTile(
              secondary: const Icon(Icons.fingerprint),
              title: const Text('App lock'),
              subtitle: Text(
                lock.supported
                    ? 'Ask for Face ID, fingerprint or passcode when opening the app.'
                    : 'Set a screen lock on this phone to use the app lock.',
              ),
              value: lock.enabled,
              onChanged: lock.supported
                  ? (v) async {
                      final ok = await lock.setEnabled(v);
                      if (!ok && context.mounted) {
                        showMessage(context, "Couldn't confirm it's you.", error: true);
                      }
                    }
                  : null,
            ),
          ),
          ListTile(
            leading: Icon(
              me?.mfaEnabled == true ? Icons.verified_user_outlined : Icons.gpp_maybe_outlined,
            ),
            title: Text(
              me?.mfaEnabled == true ? 'Two-step sign-in is on' : 'Two-step sign-in is off',
            ),
            subtitle: const Text('Manage it on the web dashboard under Settings → Security.'),
          ),
          const Divider(),
          ListTile(
            leading: Icon(Icons.logout, color: theme.colorScheme.error),
            title: Text('Sign out', style: TextStyle(color: theme.colorScheme.error)),
            subtitle: const Text('This phone will stop receiving alerts.'),
            onTap: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('Sign out?'),
                  content: const Text('You will stop receiving alerts on this phone.'),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Cancel'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Sign out'),
                    ),
                  ],
                ),
              );
              if (ok == true) await session.signOut();
            },
          ),
          const SizedBox(height: 24),
          Center(
            child: Text(
              '${AppConfig.productName} · version ${AppConfig.appVersion}',
              style: theme.textTheme.bodySmall,
            ),
          ),
          const SizedBox(height: 4),
          const PoweredBy(),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Future<void> _testPush(BuildContext context) async {
    try {
      final r = await session.api.post('/me/push-devices/test', org: false) as Json;
      if (context.mounted) showMessage(context, r['message'] as String);
    } catch (e) {
      if (context.mounted) showMessage(context, errorText(e), error: true);
    }
  }

  void _switchOrg(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final m in session.me!.memberships)
              ListTile(
                title: Text(m.organisationName),
                subtitle: Text(m.roleLabel),
                trailing: m.organisationId == session.orgId ? const Icon(Icons.check) : null,
                onTap: () {
                  session.selectOrganisation(m.organisationId);
                  Navigator.pop(context);
                },
              ),
          ],
        ),
      ),
    );
  }
}

String _initials(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return '?';
  return (parts.first[0] + (parts.length > 1 ? parts.last[0] : '')).toUpperCase();
}

class _Header extends StatelessWidget {
  const _Header(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
    child: Text(text, style: Theme.of(context).textTheme.labelLarge),
  );
}

class _PushLevel extends StatefulWidget {
  const _PushLevel({required this.session});

  final Session session;

  @override
  State<_PushLevel> createState() => _PushLevelState();
}

class _PushLevelState extends State<_PushLevel> {
  Json? _prefs;

  @override
  void initState() {
    super.initState();
    widget.session.api
        .get('/notifications/preferences')
        .then((r) {
          if (mounted) setState(() => _prefs = r as Json);
        })
        .catchError((_) {});
  }

  Future<void> _set(String level) async {
    final next = {...?_prefs, 'push_min_severity': level};
    try {
      final r = await widget.session.api.put('/notifications/preferences', next) as Json;
      if (!mounted) return;
      setState(() => _prefs = r);
      showMessage(context, 'Saved.');
    } catch (e) {
      if (mounted) showMessage(context, errorText(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final current = _prefs?['push_min_severity'] as String?;
    return ListTile(
      leading: const Icon(Icons.tune),
      title: const Text('Push me about'),
      subtitle: Text(current == null ? '…' : _levels[current] ?? current),
      trailing: const Icon(Icons.chevron_right),
      onTap: current == null
          ? null
          : () async {
              final picked = await showModalBottomSheet<String>(
                context: context,
                showDragHandle: true,
                builder: (context) => SafeArea(
                  child: RadioGroup<String>(
                    groupValue: current,
                    onChanged: (v) => Navigator.pop(context, v),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        for (final e in _levels.entries)
                          RadioListTile<String>(value: e.key, title: Text(e.value)),
                      ],
                    ),
                  ),
                ),
              );
              if (picked != null && picked != current) await _set(picked);
            },
    );
  }
}

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.session});

  final Session session;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  final _loader = GlobalKey<LoaderState<List<AppNotification>>>();

  Future<void> _markAllRead() async {
    try {
      await widget.session.api.post('/notifications/read', body: {});
      await _loader.currentState?.reload();
    } catch (e) {
      if (mounted) showMessage(context, errorText(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [TextButton(onPressed: _markAllRead, child: const Text('Mark all read'))],
      ),
      body: Loader<List<AppNotification>>(
        key: _loader,
        load: () async {
          final r = await session.api.get('/notifications', query: {'limit': 50}) as Json;
          return (r['items'] as List).cast<Json>().map(AppNotification.new).toList();
        },
        builder: (context, items, reload) {
          if (items.isEmpty) {
            return const EmptyView(icon: Icons.inbox_outlined, title: "You're all caught up");
          }
          return ListView.separated(
            itemCount: items.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, i) {
              final n = items[i];
              return ListTile(
                leading: n.severity == null
                    ? const Icon(Icons.info_outline)
                    : SeverityBar(n.severity!),
                title: Text(
                  n.title,
                  style: TextStyle(fontWeight: n.read ? FontWeight.normal : FontWeight.w600),
                ),
                subtitle: Text(
                  '${n.body}\n${timeAgo(n.createdAt)}',
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                isThreeLine: true,
                onTap: n.link == null
                    ? null
                    : () async {
                        session.api
                            .post(
                              '/notifications/read',
                              body: {
                                'ids': [n.id],
                              },
                            )
                            .ignore();
                        openLink(context, n.link!);
                      },
              );
            },
          );
        },
      ),
    );
  }
}
