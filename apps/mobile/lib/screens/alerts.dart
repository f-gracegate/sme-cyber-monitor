import 'package:flutter/material.dart';

import '../api/models.dart';
import '../core/session.dart';
import '../core/ui.dart';
import 'incidents.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key, required this.session});

  final Session session;

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  String? _severity;
  bool _resolved = false;

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    return Scaffold(
      appBar: AppBar(title: const Text('Alerts')),
      body: Column(
        children: [
          SizedBox(
            height: 52,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              children: [
                for (final s in [null, 'critical', 'high', 'medium', 'low'])
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(s == null ? 'All' : severityLabels[s]!),
                      selected: _severity == s,
                      onSelected: (_) => setState(() => _severity = s),
                    ),
                  ),
                FilterChip(
                  label: const Text('Resolved'),
                  selected: _resolved,
                  onSelected: (v) => setState(() => _resolved = v),
                ),
              ],
            ),
          ),
          Expanded(
            child: Loader<PageOf<Alert>>(
              key: ValueKey('${session.orgId}-$_severity-$_resolved'),
              load: () async => PageOf(
                await session.api.get(
                  '/alerts',
                  query: {
                    'page_size': 50,
                    'severity': ?_severity,
                    if (_resolved) 'status': ['resolved'],
                  },
                ) as Json,
                Alert.new,
              ),
              builder: (context, page, reload) {
                if (page.items.isEmpty) {
                  return EmptyView(
                    icon: Icons.verified_user_outlined,
                    title: _resolved ? 'No resolved alerts' : 'No open alerts',
                    message: _resolved ? null : "Nothing needs your attention right now.",
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                  itemCount: page.items.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final a = page.items[i];
                    return Card(
                      child: ListTile(
                        leading: SeverityBar(a.severity),
                        title: Text(a.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                        subtitle: Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Wrap(
                            spacing: 6,
                            runSpacing: 4,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              SeverityChip(a.severity),
                              StatusChip(alertStatusLabels[a.status] ?? a.status),
                              Text('${a.asset?.name ?? ''} · ${timeAgo(a.lastSeen)}'),
                            ],
                          ),
                        ),
                        onTap: () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => AlertDetailScreen(session: session, alertId: a.id),
                            ),
                          );
                          reload();
                        },
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class AlertDetailScreen extends StatefulWidget {
  const AlertDetailScreen({super.key, required this.session, required this.alertId});

  final Session session;
  final String alertId;

  @override
  State<AlertDetailScreen> createState() => _AlertDetailScreenState();
}

class _AlertDetailScreenState extends State<AlertDetailScreen> {
  final _loader = GlobalKey<LoaderState<AlertDetail>>();
  bool _busy = false;

  Future<void> _setStatus(String status, {String? note}) async {
    setState(() => _busy = true);
    try {
      await widget.session.api.patch('/alerts/${widget.alertId}', {
        'status': status,
        'note': ?note,
      });
      if (!mounted) return;
      showMessage(context, status == 'resolved' ? 'Alert resolved.' : 'Alert updated.');
      await _loader.currentState?.reload();
    } catch (e) {
      if (mounted) showMessage(context, errorText(e), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resolve() async {
    final note = await promptText(
      context,
      title: 'Resolve alert',
      label: 'What was done? (optional)',
      action: 'Resolve',
      optional: true,
    );
    if (note != null) await _setStatus('resolved', note: note.isEmpty ? null : note);
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final manage = session.can('alerts:manage');
    return Scaffold(
      appBar: AppBar(title: const Text('Alert')),
      body: Loader<AlertDetail>(
        key: _loader,
        load: () async => AlertDetail(await session.api.get('/alerts/${widget.alertId}') as Json),
        builder: (context, a, reload) {
          final theme = Theme.of(context);
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Wrap(
                spacing: 6,
                children: [
                  SeverityChip(a.severity),
                  StatusChip(alertStatusLabels[a.status] ?? a.status),
                  if (a.occurrences > 1) StatusChip('Seen ${a.occurrences} times'),
                ],
              ),
              const SizedBox(height: 10),
              Text(a.title, style: theme.textTheme.titleLarge),
              const SizedBox(height: 4),
              Text(
                '${a.asset?.name ?? ''}${a.asset != null ? ' · ${a.asset!.identifier}' : ''}',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              Text(
                'First seen ${formatDateTime(a.firstSeen)} · last ${timeAgo(a.lastSeen)}',
                style: theme.textTheme.bodySmall,
              ),
              if (a.incidentId != null) ...[
                const SizedBox(height: 12),
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.emergency_outlined),
                    title: Text('Part of ${a.incidentReference}'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) =>
                            IncidentDetailScreen(session: session, incidentId: a.incidentId!),
                      ),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              _Section(title: 'What we found', body: a.description),
              _Section(title: 'Why it matters', body: a.impact),
              _Section(title: 'What to do', body: a.recommendation),
              if (a.status == 'resolved')
                _Section(
                  title: 'Resolved',
                  body: [
                    if (a.resolvedBy != null) 'By ${a.resolvedBy}.',
                    if (a.resolutionNote != null) a.resolutionNote!,
                  ].join(' '),
                ),
              if (manage && a.status != 'resolved') ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    if (a.status == 'new')
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _busy ? null : () => _setStatus('acknowledged'),
                          child: const Text("I'm on it"),
                        ),
                      ),
                    if (a.status == 'new') const SizedBox(width: 8),
                    Expanded(
                      child: FilledButton(
                        onPressed: _busy ? null : _resolve,
                        child: const Text('Resolve'),
                      ),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 24),
            ],
          );
        },
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    if (body.trim().isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(body, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}

/// A one-field dialog. Returns null when cancelled, or the (possibly empty) text.
Future<String?> promptText(
  BuildContext context, {
  required String title,
  required String label,
  required String action,
  bool optional = false,
  int maxLines = 4,
}) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, setState) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          minLines: 2,
          maxLines: maxLines,
          decoration: InputDecoration(labelText: label),
          onChanged: (_) => setState(() {}),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: optional || controller.text.trim().isNotEmpty
                ? () => Navigator.pop(context, controller.text.trim())
                : null,
            child: Text(action),
          ),
        ],
      ),
    ),
  );
}
