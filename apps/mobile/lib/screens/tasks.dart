import 'package:flutter/material.dart';

import '../api/models.dart';
import '../core/session.dart';
import '../core/ui.dart';

/// The person's own remediation and response tasks.
class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key, required this.session, this.embedded = false});

  final Session session;
  final bool embedded;

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  bool _done = false;

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final body = Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
          child: SegmentedButton<bool>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: false, label: Text('To do')),
              ButtonSegment(value: true, label: Text('Finished')),
            ],
            selected: {_done},
            onSelectionChanged: (v) => setState(() => _done = v.first),
          ),
        ),
        Expanded(
          child: Loader<PageOf<Task>>(
            key: ValueKey('${session.orgId}-$_done'),
            load: () async => PageOf(
              await session.api.get(
                '/remediation-tasks',
                query: {
                  'mine': true,
                  'page_size': 100,
                  'status': _done ? ['verified', 'cancelled'] : ['open', 'in_progress', 'done'],
                },
              ) as Json,
              Task.new,
            ),
            builder: (context, page, reload) {
              if (page.items.isEmpty) {
                return EmptyView(
                  icon: Icons.task_alt,
                  title: _done ? 'Nothing finished yet' : 'No tasks for you',
                  message: _done ? null : 'Fixes and response tasks assigned to you appear here.',
                );
              }
              return ListView(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                children: [
                  for (final t in page.items)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 4),
                          child: TaskTile(session: session, task: t, onChanged: reload),
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
        ),
      ],
    );
    if (widget.embedded) return body;
    return Scaffold(
      appBar: AppBar(title: const Text('My tasks')),
      body: body,
    );
  }
}

/// One task, with the progress buttons the person is allowed to use.
class TaskTile extends StatefulWidget {
  const TaskTile({
    super.key,
    required this.session,
    required this.task,
    required this.onChanged,
    this.showContext = true,
  });

  final Session session;
  final Task task;
  final Future<void> Function() onChanged;
  final bool showContext;

  @override
  State<TaskTile> createState() => _TaskTileState();
}

class _TaskTileState extends State<TaskTile> {
  bool _busy = false;

  Future<void> _set(String status) async {
    setState(() => _busy = true);
    try {
      final r = await widget.session.api.patch('/remediation-tasks/${widget.task.id}', {
        'status': status,
      }) as Json;
      if (!mounted) return;
      final t = Task(r);
      showMessage(
        context,
        t.status == 'verified'
            ? 'Done and verified.'
            : t.status == 'done'
            ? 'Marked done. It will be verified when monitoring confirms the fix.'
            : 'Task updated.',
      );
      await widget.onChanged();
    } catch (e) {
      if (mounted) showMessage(context, errorText(e), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.task;
    final theme = Theme.of(context);
    final manage = widget.session.can('remediation:manage');
    final mine = t.assignee?.id == widget.session.me?.id;
    final buttons = <Widget>[
      if (!t.isClosed && (manage || mine)) ...[
        if (t.status == 'open')
          OutlinedButton(
            onPressed: _busy ? null : () => _set('in_progress'),
            child: const Text('Start'),
          ),
        if (t.status == 'open' || t.status == 'in_progress')
          FilledButton(
            onPressed: _busy ? null : () => _set('done'),
            child: const Text('Mark done'),
          ),
        if (manage && t.status == 'done')
          FilledButton(
            onPressed: _busy ? null : () => _set('verified'),
            child: const Text('Verify'),
          ),
      ],
    ];
    final meta = <String>[
      t.assignee?.name ?? 'Unassigned',
      if (t.dueAt != null) '${t.overdue ? 'Overdue since' : 'Due'} ${formatDate(t.dueAt!)}',
      if (widget.showContext && t.incidentReference != null) t.incidentReference!,
      if (widget.showContext && t.assetName != null) t.assetName!,
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            t.title,
            style: theme.textTheme.titleSmall?.copyWith(
              decoration: t.isClosed ? TextDecoration.lineThrough : null,
            ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              SeverityChip(t.priority),
              StatusChip(taskStatusLabels[t.status] ?? t.status),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            meta.join(' · '),
            style: theme.textTheme.bodySmall?.copyWith(
              color: t.overdue ? Brand.severity['critical'] : theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (t.description.isNotEmpty && widget.showContext) ...[
            const SizedBox(height: 6),
            Text(t.description, maxLines: 3, overflow: TextOverflow.ellipsis),
          ],
          if (buttons.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 8, children: buttons),
          ],
        ],
      ),
    );
  }
}
