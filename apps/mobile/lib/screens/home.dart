import 'dart:async';

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../core/app_lock.dart';
import '../core/push.dart';
import '../core/session.dart';
import '../core/ui.dart';
import 'alerts.dart';
import 'incidents.dart';
import 'more.dart';
import 'tasks.dart';

/// Bottom navigation: the triage tools an owner or IT person needs away from a desk.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.session, required this.push, required this.lock});

  final Session session;
  final PushService push;
  final AppLock lock;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;
  StreamSubscription? _foreground;

  Session get session => widget.session;

  @override
  void initState() {
    super.initState();
    session.addListener(_openPendingLink);
    WidgetsBinding.instance.addPostFrameCallback((_) => _openPendingLink());
    _foreground = widget.push.foreground.stream.listen((m) {
      if (!mounted) return;
      final title = m.notification?.title ?? 'New alert';
      final link = m.data['link'] as String?;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$title\n${m.notification?.body ?? ''}'.trim()),
          behavior: SnackBarBehavior.floating,
          action: link == null
              ? null
              : SnackBarAction(label: 'View', onPressed: () => openLink(context, link)),
        ),
      );
    });
    // Register this phone for pushes once someone is signed in and has a workspace.
    widget.push.enable();
  }

  @override
  void dispose() {
    session.removeListener(_openPendingLink);
    _foreground?.cancel();
    super.dispose();
  }

  void _openPendingLink() {
    final link = session.pendingLink;
    if (link == null || !mounted) return;
    session.takePendingLink();
    openLink(context, link);
  }

  @override
  Widget build(BuildContext context) {
    final tabs = <({String label, IconData icon, IconData selected, Widget page})>[
      (
        label: 'Overview',
        icon: Icons.space_dashboard_outlined,
        selected: Icons.space_dashboard,
        page: OverviewScreen(session: session, onTab: (i) => setState(() => _tab = i)),
      ),
      if (session.can('alerts:read'))
        (
          label: 'Alerts',
          icon: Icons.notifications_active_outlined,
          selected: Icons.notifications_active,
          page: AlertsScreen(session: session),
        ),
      (
        label: 'Incidents',
        icon: Icons.emergency_outlined,
        selected: Icons.emergency,
        page: IncidentsScreen(session: session),
      ),
      (
        label: 'Tasks',
        icon: Icons.task_alt_outlined,
        selected: Icons.task_alt,
        page: TasksScreen(session: session),
      ),
      (
        label: 'More',
        icon: Icons.menu,
        selected: Icons.menu_open,
        page: MoreScreen(session: session, push: widget.push, lock: widget.lock),
      ),
    ];
    final index = _tab.clamp(0, tabs.length - 1);
    return Scaffold(
      body: IndexedStack(index: index, children: [for (final t in tabs) t.page]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: [
          for (final t in tabs)
            NavigationDestination(
              icon: Icon(t.icon),
              selectedIcon: Icon(t.selected),
              label: t.label,
            ),
        ],
      ),
    );
  }
}

/// Opens an in-app link from a notification, such as `/alerts/{id}` or `/incidents/{id}`.
void openLink(BuildContext context, String link) {
  final session = SessionScope.of(context);
  final parts = Uri.parse(link).pathSegments;
  Widget? page;
  if (parts.length == 2 && parts[0] == 'alerts') {
    page = AlertDetailScreen(session: session, alertId: parts[1]);
  } else if (parts.length == 2 && parts[0] == 'incidents') {
    page = IncidentDetailScreen(session: session, incidentId: parts[1]);
  } else if (parts.isNotEmpty && parts[0] == 'remediation') {
    page = Scaffold(
      appBar: AppBar(title: const Text('My tasks')),
      body: TasksScreen(session: session, embedded: true),
    );
  }
  if (page == null) {
    showMessage(context, 'Open this on the web dashboard: $link');
    return;
  }
  Navigator.of(context).push(MaterialPageRoute(builder: (_) => page!));
}

/// Gives deep widgets (like [openLink]) access to the session without threading it through.
class SessionScope extends InheritedNotifier<Session> {
  const SessionScope({super.key, required Session session, required super.child})
    : super(notifier: session);

  static Session of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<SessionScope>()!.notifier!;
}

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key, required this.session, required this.onTab});

  final Session session;
  final void Function(int tab) onTab;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final membership = session.membership;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(membership?.organisationName ?? 'Overview'),
            Text(
              membership?.roleLabel ?? '',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Notifications',
            icon: const Icon(Icons.inbox_outlined),
            onPressed: () =>
                Navigator.of(context)
                    .push(MaterialPageRoute(builder: (_) => NotificationsScreen(session: session))),
          ),
        ],
      ),
      body: Loader<Overview>(
        key: ValueKey(session.orgId),
        load: () async => Overview(await session.api.get('/overview') as Json),
        builder: (context, o, reload) {
          final alertsTab = session.can('alerts:read') ? 1 : -1;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _ScoreCard(overview: o),
              const SizedBox(height: 12),
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 1.6,
                children: [
                  _Stat(
                    label: 'Open alerts',
                    value: '${o.openAlerts}',
                    hint:
                        '${(o.alertsBySeverity['critical'] ?? 0) + (o.alertsBySeverity['high'] ?? 0)} urgent',
                    urgent: (o.alertsBySeverity['critical'] ?? 0) > 0,
                    onTap: alertsTab < 0 ? null : () => onTab(alertsTab),
                  ),
                  _Stat(
                    label: 'Open incidents',
                    value: '${o.openIncidents}',
                    hint: 'Being handled',
                    urgent: o.openIncidents > 0,
                    onTap: () => onTab(alertsTab < 0 ? 1 : 2),
                  ),
                  _Stat(
                    label: 'Overdue tasks',
                    value: '${o.overdueTasks}',
                    hint: 'Past their due date',
                    urgent: o.overdueTasks > 0,
                    onTap: () => onTab(alertsTab < 0 ? 2 : 3),
                  ),
                  _Stat(
                    label: 'Monitored',
                    value: '${o.monitoredAssets}/${o.monitorableAssets}',
                    hint: 'Assets reporting',
                  ),
                ],
              ),
              if (o.recentAlerts.isNotEmpty) ...[
                const SizedBox(height: 20),
                Text('Latest alerts', style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Card(
                  child: Column(
                    children: [
                      for (final a in o.recentAlerts.take(5))
                        ListTile(
                          leading: SeverityBar(a.severity),
                          title: Text(a.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                          subtitle: Text('${a.asset} · ${timeAgo(a.lastSeen)}'),
                          onTap: () => openLink(context, '/alerts/${a.id}'),
                        ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 24),
              const PoweredBy(),
            ],
          );
        },
      ),
      floatingActionButton: session.can('incidents:report')
          ? FloatingActionButton.extended(
              heroTag: 'report-overview',
              onPressed: () => showReportIncident(context, session),
              icon: const Icon(Icons.campaign_outlined),
              label: const Text('Report incident'),
            )
          : null,
    );
  }
}

class _ScoreCard extends StatelessWidget {
  const _ScoreCard({required this.overview});

  final Overview overview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final score = overview.postureScore;
    final color = score == null
        ? theme.colorScheme.outline
        : score >= 80
        ? const Color(0xFF16A34A)
        : score >= 60
        ? const Color(0xFFD97706)
        : const Color(0xFFDC2626);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            SizedBox(
              width: 84,
              height: 84,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  CircularProgressIndicator(
                    value: (score ?? 0) / 100,
                    strokeWidth: 7,
                    color: color,
                    backgroundColor: color.withValues(alpha: 0.15),
                  ),
                  Text(
                    score?.toString() ?? '—',
                    style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Security posture', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(
                    overview.postureNote,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  if (score != null)
                    Text(
                      'Confidence ${overview.postureConfidence}%',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({
    required this.label,
    required this.value,
    required this.hint,
    this.urgent = false,
    this.onTap,
  });

  final String label;
  final String value;
  final String hint;
  final bool urgent;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: theme.textTheme.bodySmall),
              Text(
                value,
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: urgent ? Brand.severity['critical'] : null,
                ),
              ),
              Text(
                hint,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
