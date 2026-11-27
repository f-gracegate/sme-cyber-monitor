import 'package:flutter/material.dart';

import '../api/models.dart';
import '../core/session.dart';
import '../core/ui.dart';
import 'alerts.dart';
import 'tasks.dart';

class IncidentsScreen extends StatefulWidget {
  const IncidentsScreen({super.key, required this.session});

  final Session session;

  @override
  State<IncidentsScreen> createState() => _IncidentsScreenState();
}

class _IncidentsScreenState extends State<IncidentsScreen> {
  String _view = 'active';
  int _version = 0;

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final responder = session.can('incidents:read');
    final views = {
      'active': 'Active',
      if (session.can('incidents:manage')) 'mine': 'Mine',
      'all': 'All',
    };
    return Scaffold(
      appBar: AppBar(title: Text(responder ? 'Incidents' : 'My reports')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
            child: SegmentedButton<String>(
              showSelectedIcon: false,
              segments: [
                for (final e in views.entries) ButtonSegment(value: e.key, label: Text(e.value)),
              ],
              selected: {_view},
              onSelectionChanged: (v) => setState(() => _view = v.first),
            ),
          ),
          Expanded(
            child: Loader<PageOf<Incident>>(
              key: ValueKey('${session.orgId}-$_view-$_version'),
              load: () async => PageOf(
                await session.api.get(
                  '/incidents',
                  query: {
                    'page_size': 50,
                    if (_view == 'active') 'status': ['open', 'investigating', 'contained'],
                    if (_view == 'mine') 'mine': true,
                  },
                ) as Json,
                Incident.new,
              ),
              builder: (context, page, reload) {
                if (page.items.isEmpty) {
                  return EmptyView(
                    icon: Icons.shield_outlined,
                    title: _view == 'active' ? 'No active incidents' : 'No incidents',
                    message: responder
                        ? null
                        : 'If something looks wrong (a strange email, a lost laptop), report it '
                              'and the security team will take it from there.',
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 96),
                  itemCount: page.items.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final inc = page.items[i];
                    return Card(
                      child: ListTile(
                        leading: SeverityBar(inc.severity),
                        title: Text(inc.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                        subtitle: Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Wrap(
                            spacing: 6,
                            runSpacing: 4,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              Text(
                                inc.reference,
                                style: const TextStyle(fontWeight: FontWeight.w600),
                              ),
                              SeverityChip(inc.severity),
                              StatusChip(incidentStatusLabels[inc.status] ?? inc.status),
                              Text(inc.owner?.name ?? 'No owner'),
                            ],
                          ),
                        ),
                        onTap: () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) =>
                                  IncidentDetailScreen(session: session, incidentId: inc.id),
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
      floatingActionButton: session.can('incidents:report')
          ? FloatingActionButton.extended(
              heroTag: 'report-incidents',
              onPressed: () async {
                if (await showReportIncident(context, session) && mounted) {
                  setState(() => _version++);
                }
              },
              icon: const Icon(Icons.campaign_outlined),
              label: const Text('Report'),
            )
          : null,
    );
  }
}

/// Report a suspected incident. Returns true when one was created.
Future<bool> showReportIncident(BuildContext context, Session session) async {
  final created = await showModalBottomSheet<Incident>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _ReportIncidentSheet(session: session),
  );
  if (created == null || !context.mounted) return false;
  showMessage(context, '${created.reference} reported. The security team has been told.');
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => IncidentDetailScreen(session: session, incidentId: created.id),
    ),
  );
  return true;
}

class _ReportIncidentSheet extends StatefulWidget {
  const _ReportIncidentSheet({required this.session});

  final Session session;

  @override
  State<_ReportIncidentSheet> createState() => _ReportIncidentSheetState();
}

class _ReportIncidentSheetState extends State<_ReportIncidentSheet> {
  final _title = TextEditingController();
  final _summary = TextEditingController();
  String _category = 'phishing';
  String? _severity;
  String? _error;
  bool _busy = false;

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await widget.session.api.post(
        '/incidents',
        body: {
          'title': _title.text.trim(),
          'summary': _summary.text.trim(),
          'category': _category,
          'severity': ?_severity,
        },
      );
      if (mounted) Navigator.pop(context, Incident(r as Json));
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final responder = widget.session.can('incidents:manage');
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, MediaQuery.of(context).viewInsets.bottom + 20),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Report an incident', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            const Text("Tell us what happened. Don't worry about getting the details perfect."),
            const SizedBox(height: 16),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            DropdownButtonFormField<String>(
              initialValue: _category,
              decoration: const InputDecoration(labelText: 'What kind of problem?'),
              items: [
                for (final e in incidentCategories.entries)
                  DropdownMenuItem(value: e.key, child: Text(e.value)),
              ],
              onChanged: (v) => setState(() => _category = v ?? 'other'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _title,
              maxLength: 200,
              decoration: const InputDecoration(
                labelText: 'Short description',
                hintText: 'e.g. Suspicious email asking for MoMo PIN',
              ),
              onChanged: (_) => setState(() {}),
            ),
            TextField(
              controller: _summary,
              minLines: 3,
              maxLines: 6,
              decoration: const InputDecoration(
                labelText: 'What happened? (optional)',
                hintText: 'When did you notice it? Did you click anything or share details?',
              ),
            ),
            if (responder) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<String?>(
                initialValue: _severity,
                decoration: const InputDecoration(labelText: 'Severity'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Medium (default)')),
                  for (final s in ['critical', 'high', 'medium', 'low'])
                    DropdownMenuItem(value: s, child: Text(severityLabels[s]!)),
                ],
                onChanged: (v) => setState(() => _severity = v),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _busy || _title.text.trim().isEmpty ? null : _submit,
              child: Text(_busy ? 'Sending…' : 'Send report'),
            ),
          ],
        ),
      ),
    );
  }
}

class IncidentDetailScreen extends StatefulWidget {
  const IncidentDetailScreen({super.key, required this.session, required this.incidentId});

  final Session session;
  final String incidentId;

  @override
  State<IncidentDetailScreen> createState() => _IncidentDetailScreenState();
}

class _IncidentDetailScreenState extends State<IncidentDetailScreen> {
  final _loader = GlobalKey<LoaderState<IncidentDetail>>();
  bool _busy = false;

  Session get session => widget.session;

  Future<void> _update(Map<String, dynamic> body, String done) async {
    setState(() => _busy = true);
    try {
      await session.api.patch('/incidents/${widget.incidentId}', body);
      if (!mounted) return;
      showMessage(context, done);
      await _loader.currentState?.reload();
    } catch (e) {
      if (mounted) showMessage(context, errorText(e), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addNote() async {
    final note = await promptText(context, title: 'Add an update', label: 'Update', action: 'Add');
    if (note == null || note.isEmpty) return;
    try {
      await session.api.post('/incidents/${widget.incidentId}/notes', body: {'body': note});
      if (!mounted) return;
      showMessage(context, 'Update added.');
      await _loader.currentState?.reload();
    } catch (e) {
      if (mounted) showMessage(context, errorText(e), error: true);
    }
  }

  Future<void> _close() async {
    final result = await showDialog<(String, String)>(
      context: context,
      builder: (_) => const _CloseDialog(),
    );
    if (result == null) return;
    await _update({
      'status': 'closed',
      'closure_reason': result.$1,
      if (result.$2.isNotEmpty) 'resolution_summary': result.$2,
    }, 'Incident closed.');
  }

  List<Widget> _actions(IncidentDetail inc) {
    if (!inc.canManage) return const [];
    final next = <(String, String, String)>[
      if (inc.status == 'open') ('investigating', 'Start investigating', 'Investigation started.'),
      if (inc.status == 'open' || inc.status == 'investigating')
        ('contained', 'Mark contained', 'Marked as contained.'),
      if (inc.status == 'contained' || inc.status == 'investigating')
        ('resolved', 'Mark resolved', 'Marked as resolved.'),
    ];
    return [
      for (final (i, a) in next.indexed)
        i == next.length - 1
            ? FilledButton(
                onPressed: _busy ? null : () => _update({'status': a.$1}, a.$3),
                child: Text(a.$2),
              )
            : OutlinedButton(
                onPressed: _busy ? null : () => _update({'status': a.$1}, a.$3),
                child: Text(a.$2),
              ),
      if (inc.status == 'resolved')
        FilledButton(onPressed: _busy ? null : _close, child: const Text('Close incident')),
      if (inc.status == 'resolved' || inc.status == 'closed')
        OutlinedButton(
          onPressed: _busy
              ? null
              : () => _update({'status': 'investigating'}, 'Incident reopened.'),
          child: const Text('Reopen'),
        ),
      if (inc.owner?.id != session.me?.id && inc.status != 'closed')
        TextButton(
          onPressed: _busy
              ? null
              : () => _update({'owner_id': session.me!.id}, "You're now the owner."),
          child: const Text('Take ownership'),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Incident')),
      body: Loader<IncidentDetail>(
        key: _loader,
        load: () async =>
            IncidentDetail(await session.api.get('/incidents/${widget.incidentId}') as Json),
        builder: (context, inc, reload) {
          final theme = Theme.of(context);
          final muted = theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          );
          final actions = _actions(inc);
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  Text(inc.reference, style: theme.textTheme.labelLarge),
                  SeverityChip(inc.severity),
                  StatusChip(incidentStatusLabels[inc.status] ?? inc.status),
                ],
              ),
              const SizedBox(height: 8),
              Text(inc.title, style: theme.textTheme.titleLarge),
              const SizedBox(height: 4),
              Text(
                '${incidentCategories[inc.category] ?? inc.category} · opened ${formatDateTime(inc.createdAt)}'
                '${inc.reporter != null ? ' by ${inc.reporter!.name}' : ''}',
                style: muted,
              ),
              Text('Owner: ${inc.owner?.name ?? 'nobody yet'}', style: muted),
              if (actions.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(spacing: 8, runSpacing: 8, children: actions),
              ],
              if (inc.summary.isNotEmpty) ...[const SizedBox(height: 16), Text(inc.summary)],
              if (inc.assets.isNotEmpty) ...[
                _heading(context, 'Affected assets'),
                for (final a in inc.assets)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.dns_outlined),
                    title: Text(a.name),
                    subtitle: Text(a.identifier),
                  ),
              ],
              if (inc.alerts.isNotEmpty) ...[
                _heading(context, 'Related alerts'),
                for (final a in inc.alerts)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: SeverityBar(a.severity),
                    title: Text(a.title),
                    subtitle: Text(a.asset),
                    onTap: session.can('alerts:read')
                        ? () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => AlertDetailScreen(session: session, alertId: a.id),
                            ),
                          )
                        : null,
                  ),
              ],
              if (inc.tasks.isNotEmpty) ...[
                _heading(context, 'Response tasks'),
                for (final t in inc.tasks)
                  TaskTile(session: session, task: t, onChanged: reload, showContext: false),
              ],
              _heading(
                context,
                'Timeline',
                trailing: TextButton.icon(
                  onPressed: _addNote,
                  icon: const Icon(Icons.add_comment_outlined, size: 18),
                  label: const Text('Add update'),
                ),
              ),
              for (final e in inc.timeline.reversed)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 6, right: 10),
                        child: Icon(
                          e.type == 'note' ? Icons.chat_bubble_outline : Icons.circle,
                          size: e.type == 'note' ? 16 : 8,
                          color: theme.colorScheme.outline,
                        ),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (e.body != null) Text(e.body!),
                            Text('${e.actor ?? 'System'} · ${formatDateTime(e.at)}', style: muted),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 24),
            ],
          );
        },
      ),
    );
  }

  Widget _heading(BuildContext context, String text, {Widget? trailing}) => Padding(
    padding: const EdgeInsets.only(top: 20, bottom: 4),
    child: Row(
      children: [
        Expanded(child: Text(text, style: Theme.of(context).textTheme.titleMedium)),
        ?trailing,
      ],
    ),
  );
}

class _CloseDialog extends StatefulWidget {
  const _CloseDialog();

  @override
  State<_CloseDialog> createState() => _CloseDialogState();
}

class _CloseDialogState extends State<_CloseDialog> {
  static const reasons = {
    'resolved': 'Resolved',
    'false_positive': 'False alarm',
    'duplicate': 'Duplicate',
    'accepted_risk': 'Risk accepted',
    'other': 'Other',
  };
  String _reason = 'resolved';
  final _lessons = TextEditingController();

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Close incident'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _reason,
          decoration: const InputDecoration(labelText: 'Outcome'),
          items: [
            for (final e in reasons.entries) DropdownMenuItem(value: e.key, child: Text(e.value)),
          ],
          onChanged: (v) => setState(() => _reason = v ?? 'resolved'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _lessons,
          minLines: 2,
          maxLines: 4,
          decoration: const InputDecoration(labelText: 'Lessons learned (optional)'),
        ),
      ],
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(
        onPressed: () => Navigator.pop(context, (_reason, _lessons.text.trim())),
        child: const Text('Close incident'),
      ),
    ],
  );
}
