/// Typed views over the API's JSON. Only the fields the companion app uses are mapped.
library;

typedef Json = Map<String, dynamic>;

DateTime? _date(Object? v) => v == null ? null : DateTime.tryParse(v as String)?.toLocal();

List<Json> _list(Object? v) => (v as List? ?? const []).cast<Json>();

class Membership {
  Membership(Json j)
    : organisationId = j['organisation_id'] as String,
      organisationName = j['organisation_name'] as String,
      roleLabel = j['role_label'] as String,
      permissions = (j['permissions'] as List).cast<String>().toSet(),
      requireMfa = j['require_mfa'] as bool? ?? false;

  final String organisationId;
  final String organisationName;
  final String roleLabel;
  final Set<String> permissions;
  final bool requireMfa;
}

class Me {
  Me(Json j)
    : id = j['user']['id'] as String,
      email = j['user']['email'] as String,
      fullName = j['user']['full_name'] as String,
      mustChangePassword = j['user']['must_change_password'] as bool,
      mfaEnabled = j['user']['mfa_enabled'] as bool,
      memberships = _list(j['memberships']).map(Membership.new).toList();

  final String id;
  final String email;
  final String fullName;
  final bool mustChangePassword;
  final bool mfaEnabled;
  final List<Membership> memberships;
}

class PageOf<T> {
  PageOf(Json j, T Function(Json) parse)
    : items = _list(j['items']).map(parse).toList(),
      total = j['total'] as int;

  final List<T> items;
  final int total;
}

class AssetRef {
  AssetRef(Json j)
    : id = j['id'] as String,
      name = j['name'] as String,
      identifier = j['identifier'] as String? ?? '';

  final String id;
  final String name;
  final String identifier;
}

class Alert {
  Alert(Json j)
    : id = j['id'] as String,
      title = j['title'] as String,
      severity = j['severity'] as String,
      status = j['status'] as String,
      occurrences = j['occurrences'] as int? ?? 1,
      firstSeen = _date(j['first_seen_at'])!,
      lastSeen = _date(j['last_seen_at'])!,
      asset = j['asset'] == null ? null : AssetRef(j['asset'] as Json);

  final String id;
  final String title;
  final String severity;
  final String status;
  final int occurrences;
  final DateTime firstSeen;
  final DateTime lastSeen;
  final AssetRef? asset;
}

class AlertDetail extends Alert {
  AlertDetail(super.j)
    : description = j['finding']['description'] as String,
      impact = j['finding']['impact'] as String,
      recommendation = j['finding']['recommendation'] as String,
      incidentId = j['incident']?['id'] as String?,
      incidentReference = j['incident']?['reference'] as String?,
      acknowledgedBy = j['acknowledged_by_name'] as String?,
      resolvedBy = j['resolved_by_name'] as String?,
      resolutionNote = j['resolution_note'] as String?;

  final String description;
  final String impact;
  final String recommendation;
  final String? incidentId;
  final String? incidentReference;
  final String? acknowledgedBy;
  final String? resolvedBy;
  final String? resolutionNote;
}

class Person {
  Person(Json j) : id = j['id'] as String, name = j['name'] as String;

  final String id;
  final String name;
}

class Incident {
  Incident(Json j)
    : id = j['id'] as String,
      reference = j['reference'] as String,
      title = j['title'] as String,
      summary = j['summary'] as String? ?? '',
      severity = j['severity'] as String,
      status = j['status'] as String,
      category = j['category'] as String,
      source = j['source'] as String,
      owner = j['owner'] == null ? null : Person(j['owner'] as Json),
      reporter = j['reporter'] == null ? null : Person(j['reporter'] as Json),
      createdAt = _date(j['created_at'])!,
      updatedAt = _date(j['updated_at'])!,
      alertCount = j['alert_count'] as int? ?? 0,
      assetCount = j['asset_count'] as int? ?? 0,
      openTasks = j['open_tasks'] as int? ?? 0;

  final String id;
  final String reference;
  final String title;
  final String summary;
  final String severity;
  final String status;
  final String category;
  final String source;
  final Person? owner;
  final Person? reporter;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int alertCount;
  final int assetCount;
  final int openTasks;

  bool get isActive => const {'open', 'investigating', 'contained'}.contains(status);
}

class TimelineEntry {
  TimelineEntry(Json j)
    : type = j['event_type'] as String,
      actor = j['actor_label'] as String?,
      body = j['body'] as String?,
      at = _date(j['occurred_at'])!;

  final String type;
  final String? actor;
  final String? body;
  final DateTime at;
}

class IncidentDetail extends Incident {
  IncidentDetail(super.j)
    : assets = _list(j['assets']).map(AssetRef.new).toList(),
      alerts = _list(j['alerts'])
          .map(
            (a) => (
              id: a['id'] as String,
              title: a['title'] as String,
              severity: a['severity'] as String,
              asset: a['asset_name'] as String,
            ),
          )
          .toList(),
      timeline = _list(j['timeline']).map(TimelineEntry.new).toList(),
      tasks = _list(j['tasks']).map(Task.new).toList(),
      canManage = j['can_manage'] as bool? ?? false;

  final List<AssetRef> assets;
  final List<({String id, String title, String severity, String asset})> alerts;
  final List<TimelineEntry> timeline;
  final List<Task> tasks;
  final bool canManage;
}

class Task {
  Task(Json j)
    : id = j['id'] as String,
      kind = j['kind'] as String,
      title = j['title'] as String,
      description = j['description'] as String? ?? '',
      priority = j['priority'] as String,
      status = j['status'] as String,
      findingId = j['finding_id'] as String?,
      incidentId = j['incident_id'] as String?,
      incidentReference = j['incident_reference'] as String?,
      assetName = j['asset_name'] as String?,
      assignee = j['assignee'] == null ? null : Person(j['assignee'] as Json),
      dueAt = _date(j['due_at']),
      verifiedAt = _date(j['verified_at']),
      verification = j['verification'] as String?,
      note = j['note'] as String?,
      overdue = j['overdue'] as bool? ?? false;

  final String id;
  final String kind;
  final String title;
  final String description;
  final String priority;
  final String status;
  final String? findingId;
  final String? incidentId;
  final String? incidentReference;
  final String? assetName;
  final Person? assignee;
  final DateTime? dueAt;
  final DateTime? verifiedAt;
  final String? verification;
  final String? note;
  final bool overdue;

  bool get isClosed => status == 'verified' || status == 'cancelled';
}

class AppNotification {
  AppNotification(Json j)
    : id = j['id'] as String,
      severity = j['severity'] as String?,
      title = j['title'] as String,
      body = j['body'] as String,
      link = j['link'] as String?,
      read = j['read_at'] != null,
      createdAt = _date(j['created_at'])!;

  final String id;
  final String? severity;
  final String title;
  final String body;
  final String? link;
  final bool read;
  final DateTime createdAt;
}

class Overview {
  Overview(Json j)
    : organisationName = j['organisation_name'] as String,
      postureScore = j['posture_score'] as int?,
      postureNote = j['posture_note'] as String? ?? '',
      postureConfidence = j['posture_confidence'] as int? ?? 0,
      alertsBySeverity = (j['alerts_open_by_severity'] as Map).cast<String, int>(),
      findingsBySeverity = (j['findings_open_by_severity'] as Map).cast<String, int>(),
      openIncidents = j['open_incidents'] as int? ?? 0,
      overdueTasks = j['overdue_tasks'] as int? ?? 0,
      monitoredAssets = j['monitored_assets'] as int? ?? 0,
      monitorableAssets = j['monitorable_assets'] as int? ?? 0,
      recentAlerts = _list(j['recent_alerts'])
          .map(
            (a) => (
              id: a['id'] as String,
              title: a['title'] as String,
              severity: a['severity'] as String,
              asset: a['asset_name'] as String,
              lastSeen: _date(a['last_seen_at'])!,
            ),
          )
          .toList();

  final String organisationName;
  final int? postureScore;
  final String postureNote;
  final int postureConfidence;
  final Map<String, int> alertsBySeverity;
  final Map<String, int> findingsBySeverity;
  final int openIncidents;
  final int overdueTasks;
  final int monitoredAssets;
  final int monitorableAssets;
  final List<({String id, String title, String severity, String asset, DateTime lastSeen})>
  recentAlerts;

  int get openAlerts => alertsBySeverity.values.fold(0, (a, b) => a + b);
}
