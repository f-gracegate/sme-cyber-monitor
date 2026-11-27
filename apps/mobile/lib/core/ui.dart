import 'package:flutter/material.dart';

import '../api/api_client.dart';
import 'config.dart';

/// Brand and design tokens shared with the web app.
class Brand {
  Brand._();

  static const primary = Color(0xFF2563EB);
  static const navy = Color(0xFF101828);
  static const gracegate = Color(0xFF9333EA);

  static const severity = {
    'critical': Color(0xFFDC2626),
    'high': Color(0xFFEA580C),
    'medium': Color(0xFFD97706),
    'low': Color(0xFF2563EB),
    'informational': Color(0xFF64748B),
  };
}

ThemeData buildTheme(Brightness brightness) {
  // Keep the exact brand blue for buttons and accents, as on the web dashboard.
  final scheme = ColorScheme.fromSeed(
    seedColor: Brand.primary,
    brightness: brightness,
  ).copyWith(primary: brightness == Brightness.light ? Brand.primary : null);
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    scaffoldBackgroundColor: brightness == Brightness.light ? const Color(0xFFF8FAFC) : null,
    appBarTheme: const AppBarTheme(centerTitle: false),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
  );
}

const severityLabels = {
  'critical': 'Critical',
  'high': 'High',
  'medium': 'Medium',
  'low': 'Low',
  'informational': 'Info',
};

const alertStatusLabels = {
  'new': 'New',
  'acknowledged': 'Acknowledged',
  'investigating': 'Investigating',
  'resolved': 'Resolved',
};

const incidentStatusLabels = {
  'open': 'Open',
  'investigating': 'Investigating',
  'contained': 'Contained',
  'resolved': 'Resolved',
  'closed': 'Closed',
};

const taskStatusLabels = {
  'open': 'To do',
  'in_progress': 'In progress',
  'done': 'Awaiting check',
  'verified': 'Verified',
  'cancelled': 'Cancelled',
};

const incidentCategories = {
  'phishing': 'Phishing or scam',
  'malware': 'Malware or virus',
  'account_compromise': 'Account compromise',
  'unauthorised_access': 'Unauthorised access',
  'intrusion': 'Network intrusion',
  'data_loss': 'Data loss or leak',
  'availability': 'Outage or availability',
  'lost_device': 'Lost or stolen device',
  'policy_violation': 'Policy violation',
  'other': 'Something else',
};

class SeverityChip extends StatelessWidget {
  const SeverityChip(this.severity, {super.key});

  final String severity;

  @override
  Widget build(BuildContext context) {
    final color = Brand.severity[severity] ?? Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Text(
        severityLabels[severity] ?? severity,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, this.color});

  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: c.withValues(alpha: 0.4)),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Text(
        label,
        style: TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.w500),
      ),
    );
  }
}

class SeverityBar extends StatelessWidget {
  const SeverityBar(this.severity, {super.key});

  final String severity;

  @override
  Widget build(BuildContext context) => Container(
    width: 4,
    height: 40,
    decoration: BoxDecoration(
      color: Brand.severity[severity] ?? Colors.grey,
      borderRadius: BorderRadius.circular(2),
    ),
  );
}

class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.icon, required this.title, this.message});

  final IconData icon;
  final String title;
  final String? message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      // Scrollable so pull-to-refresh still works on an empty list.
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 48),
        Icon(icon, size: 40, color: theme.colorScheme.outline),
        const SizedBox(height: 12),
        Text(title, textAlign: TextAlign.center, style: theme.textTheme.titleMedium),
        if (message != null) ...[
          const SizedBox(height: 6),
          Text(
            message!,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
      ],
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_outlined, size: 40, color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 12),
            Text(errorText(error), textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Try again')),
          ],
        ),
      ),
    );
  }
}

String errorText(Object error) =>
    error is ApiException ? error.message : 'Something went wrong. Try again.';

void showMessage(BuildContext context, String message, {bool error = false}) {
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: error ? Theme.of(context).colorScheme.error : null,
      behavior: SnackBarBehavior.floating,
    ),
  );
}

class PoweredBy extends StatelessWidget {
  const PoweredBy({super.key});

  @override
  Widget build(BuildContext context) => Text.rich(
    TextSpan(
      text: 'Powered by ',
      children: [
        TextSpan(
          text: AppConfig.companyName,
          style: const TextStyle(color: Brand.gracegate, fontWeight: FontWeight.w600),
        ),
      ],
    ),
    textAlign: TextAlign.center,
    style: Theme.of(context).textTheme.bodySmall,
  );
}

/// "5 min ago", "Yesterday", "3 Dec".
String timeAgo(DateTime t) {
  final d = DateTime.now().difference(t);
  if (d.inMinutes < 1) return 'Just now';
  if (d.inMinutes < 60) return '${d.inMinutes} min ago';
  if (d.inHours < 24) return '${d.inHours} h ago';
  if (d.inDays == 1) return 'Yesterday';
  if (d.inDays < 7) return '${d.inDays} days ago';
  return formatDate(t);
}

const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', //
];

String formatDate(DateTime t) =>
    '${t.day} ${_months[t.month - 1]}${t.year == DateTime.now().year ? '' : ' ${t.year}'}';

String formatDateTime(DateTime t) =>
    '${formatDate(t)}, ${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

/// Loads data for a screen and rebuilds on refresh. Keeps screens free of boilerplate.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder});

  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => LoaderState<T>();
}

class LoaderState<T> extends State<Loader<T>> {
  late Future<T> _future = widget.load();

  Future<void> reload() async {
    final next = widget.load();
    setState(() {
      _future = next;
    });
    try {
      await next;
    } catch (_) {
      // Shown by the builder.
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: _future,
      builder: (context, snap) {
        if (snap.hasError) return ErrorView(error: snap.error!, onRetry: reload);
        if (!snap.hasData) return const Center(child: CircularProgressIndicator());
        return RefreshIndicator(
          onRefresh: reload,
          child: widget.builder(context, snap.data as T, reload),
        );
      },
    );
  }
}
