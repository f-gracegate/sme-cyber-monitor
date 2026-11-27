export type User = {
  id: string;
  email: string;
  username: string | null;
  full_name: string;
  is_platform_admin: boolean;
  must_change_password: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
};

export type MembershipSummary = {
  organisation_id: string;
  organisation_name: string;
  role: string;
  role_label: string;
  permissions: string[];
  require_mfa: boolean;
};

export type Me = { user: User; memberships: MembershipSummary[] };

export type LoginResponse = { status: "ok" | "mfa_required"; mfa_token?: string; me?: Me };

export type Organisation = {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  country: string;
  timezone: string;
  phone: string | null;
  address: string | null;
  website: string | null;
  status: string;
  require_mfa: boolean;
  created_at: string;
};

export type Member = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  status: "active" | "suspended";
  department_id: string | null;
  department_name: string | null;
  mfa_enabled: boolean;
  last_login_at: string | null;
  joined_at: string;
  is_you: boolean;
};

export type Invitation = {
  id: string;
  email: string;
  role: string;
  created_at: string;
  expires_at: string;
  invited_by_email: string | null;
};

export type Department = { id: string; name: string; created_at: string };
export type RoleInfo = { value: string; label: string; permissions: string[] };

export type Asset = {
  id: string;
  name: string;
  identifier: string;
  type: string;
  category: string;
  criticality: "low" | "medium" | "high" | "critical";
  status: "active" | "archived";
  monitoring_status: string;
  risk_level: string;
  technology: string | null;
  location: string | null;
  notes: string | null;
  department_id: string | null;
  department_name: string | null;
  owner_user_id: string | null;
  owner_name: string | null;
  last_seen_at: string | null;
  last_successful_check_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Authorisation = {
  id: string;
  method: "dns_txt" | "http_file" | "attestation";
  challenge: string;
  status: "pending" | "verified" | "failed";
  failure_reason: string | null;
  created_at: string;
  last_attempt_at: string | null;
  verified_at: string | null;
  evidence: Record<string, unknown>;
};

export type VerificationInstructions = {
  method: string;
  summary: string;
  steps: string[];
  record_name: string | null;
  record_value: string | null;
  file_url: string | null;
  file_contents: string | null;
};

export type AssetDetail = Asset & {
  authorisation: Authorisation | null;
  instructions: VerificationInstructions | null;
  verification_methods: string[];
};

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type AuditEntry = {
  id: string;
  action: string;
  actor_label: string | null;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
};

export type Recommendation = {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  description: string;
  action_label: string;
  action_href: string;
};

export type Overview = OverviewMonitoring & {
  organisation_name: string;
  assets_total: number;
  assets_by_category: Record<string, number>;
  assets_by_monitoring_status: Record<string, number>;
  assets_authorised: number;
  critical_assets: number;
  members_total: number;
  members_with_mfa: number;
  privileged_without_mfa: number;
  pending_invitations: number;
  posture_score: number | null;
  posture_note: string;
  recommendations: Recommendation[];
};

export type Plan = {
  code: string;
  name: string;
  monthly_price_ghs: number | null;
  annual_price_ghs: number | null;
  asset_limit: number | null;
  member_limit: number | null;
  collector_limit: number | null;
  features: string[];
};

export type SubscriptionStatus = "trialing" | "active" | "past_due" | "expired" | "cancelled";

export type Subscription = {
  plan: Plan;
  status: SubscriptionStatus;
  billing_period: "monthly" | "annual";
  current_period_end: string | null;
  grace_until: string | null;
  days_left: number | null;
  assets_used: number;
  members_used: number;
  collectors_used: number;
  available_plans: Plan[];
  payment_provider: string;
  has_paid: boolean;
  annual_months_charged: number;
  contact_email: string;
};

export type PaymentChannel = "mobile_money" | "card";

export type Payment = {
  id: string;
  reference: string;
  plan_code: string;
  plan_name: string;
  billing_period: "monthly" | "annual";
  amount_minor: number;
  currency: string;
  channel: PaymentChannel;
  status: "pending" | "success" | "failed" | "abandoned";
  failure_reason: string | null;
  payment_method: { brand?: string; last4?: string; network?: string; phone?: string };
  receipt: string | null;
  credit_days: number;
  period_start: string | null;
  period_end: string | null;
  paid_at: string | null;
  created_at: string;
};

export type CheckoutResult = {
  reference: string;
  authorization_url: string;
  amount_minor: number;
  currency: string;
};

export type OnboardingStep = {
  id: string;
  title: string;
  description: string;
  done: boolean;
  optional: boolean;
  href: string | null;
  action_label: string | null;
};

export type Onboarding = {
  steps: OnboardingStep[];
  completed: number;
  required: number;
  required_done: number;
  complete: boolean;
  dismissed: boolean;
};

export type PushDevice = {
  id: string;
  platform: "android" | "ios";
  device_name: string | null;
  app_version: string | null;
  enabled: boolean;
  this_device: boolean;
  created_at: string;
  last_seen_at: string;
  last_error: string | null;
};

export type PlatformOrganisation = {
  id: string;
  name: string;
  industry: string | null;
  status: string;
  plan_code: string | null;
  members: number;
  assets: number;
  created_at: string;
};

// --- Monitoring (Phase 2) -------------------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low" | "informational";

export type AssetRef = {
  id: string;
  name: string;
  identifier: string;
  type: string;
  criticality: string;
};

export type Check = {
  id: string;
  asset_id: string;
  check_type: string;
  interval_minutes: number;
  enabled: boolean;
  next_run_at: string;
  last_run_at: string | null;
  last_status: "pending" | "ok" | "warning" | "failing" | "error";
  last_summary: string | null;
  consecutive_failures: number;
  asset: AssetRef | null;
};

export type CheckRun = {
  id: string;
  check_id: string;
  asset_id: string;
  check_type: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  status: string;
  summary: string;
  result: Record<string, unknown>;
};

export type MonitoringSummary = {
  checks_total: number;
  checks_enabled: number;
  by_status: Record<string, number>;
  monitored_assets: number;
  monitorable_assets: number;
  awaiting_authorisation: number;
  assets_with_check_errors: number;
};

export type Finding = {
  id: string;
  asset_id: string;
  check_type: string;
  rule_key: string;
  title: string;
  description: string;
  impact: string;
  recommendation: string;
  severity: Severity;
  score: number;
  status: "open" | "resolved" | "accepted_risk";
  evidence: Record<string, unknown>;
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
  asset: AssetRef | null;
};

export type FindingDetail = Finding & {
  open_alert_id: string | null;
  sticky: boolean;
  resolved_by_name: string | null;
};

export type Alert = {
  id: string;
  finding_id: string;
  asset_id: string;
  title: string;
  severity: Severity;
  status: "new" | "acknowledged" | "investigating" | "resolved";
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  asset: AssetRef | null;
};

export type AlertDetail = Alert & {
  finding: Finding;
  incident: { id: string; reference: string; title: string; status: string } | null;
  acknowledged_by_name: string | null;
  resolved_by_name: string | null;
};

export type AppNotification = {
  id: string;
  alert_id: string | null;
  severity: Severity | null;
  title: string;
  body: string;
  link: string | null;
  read_at: string | null;
  created_at: string;
};

export type NotificationList = { items: AppNotification[]; unread: number };

export type NotificationPreferences = {
  email_min_severity: string;
  in_app_min_severity: string;
  push_min_severity: string;
};

export type OverviewMonitoring = {
  monitored_assets: number;
  monitorable_assets: number;
  assets_with_check_errors: number;
  findings_open_by_severity: Record<Severity, number>;
  findings_by_status: Record<string, number>;
  alerts_open_by_severity: Record<Severity, number>;
  recent_alerts: {
    id: string;
    title: string;
    severity: Severity;
    status: string;
    asset_name: string;
    last_seen_at: string;
  }[];
  most_exposed_assets: {
    id: string;
    name: string;
    identifier: string;
    type: string;
    open_findings: number;
    highest_severity: Severity;
  }[];
  trend: { day: string; score: number }[];
  posture_components: Record<string, number | null>;
  posture_confidence: number;
  open_incidents: number;
  overdue_tasks: number;
  neglected_findings: number;
};

// --- Endpoints (Phase 3) --------------------------------------------------------------------

export type Endpoint = {
  id: string;
  source: "smecm_agent" | "wazuh";
  hostname: string;
  os_family: string | null;
  os_name: string | null;
  os_version: string | null;
  agent_version: string | null;
  status: "active" | "revoked";
  online: boolean;
  last_seen_at: string | null;
  last_ip: string | null;
  enrolled_at: string;
  inventory: Record<string, unknown>;
  asset: { id: string; name: string; type: string; department_name: string | null; criticality: string };
  open_alerts: number;
  open_findings: number;
  events_24h: number;
};

export type EndpointSummary = {
  total: number;
  online: number;
  offline: number;
  with_issues: number;
  events_24h: number;
};

export type SecurityEvent = {
  id: string;
  asset_id: string;
  agent_id: string;
  event_type: string;
  severity: Severity;
  summary: string;
  occurred_at: string;
  received_at: string;
  data: Record<string, unknown>;
  asset_name: string | null;
};

export type EnrolmentToken = {
  id: string;
  token_hint: string;
  label: string | null;
  asset_type: string;
  department_id: string | null;
  max_uses: number;
  uses: number;
  created_at: string;
  expires_at: string;
};

export type IntegrationKey = {
  id: string;
  kind: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
};

export type AgentRelease = { version: string; filename: string; sha256: string; size_bytes: number };

// --- Network (Phase 4) ----------------------------------------------------------------------

export type Collector = {
  id: string;
  asset_id: string;
  name: string;
  hostname: string;
  version: string | null;
  status: string;
  online: boolean;
  last_seen_at: string | null;
  last_ip: string | null;
  enrolled_at: string;
  capabilities: string[];
  sources: { name: string; type: string; events: number; last_event_at: string | null }[];
  queue_depth: number | null;
  events_24h: number;
  traffic: {
    window_seconds: number;
    connections: number;
    bytes_in: number;
    bytes_out: number;
    top_talkers: { host: string; bytes: number }[];
  } | null;
};

export type NetworkDevice = {
  id: string;
  name: string;
  identifier: string;
  type: string;
  criticality: string;
  monitoring_status: string;
  availability: "reachable" | "unreachable" | "not_probed" | "awaiting_authorisation";
  latency_ms: number | null;
  last_seen_at: string | null;
  last_checked_at: string | null;
  open_findings: number;
  events_24h: number;
};

export type NetworkSummary = {
  collectors_total: number;
  collectors_online: number;
  collector_allowance: number | null;
  devices_total: number;
  devices_reachable: number;
  devices_unreachable: number;
  devices_not_probed: number;
  sensor_deployed: boolean;
  ids_alerts_24h: Record<string, number>;
  firewall_denies_24h: number;
  config_changes_24h: number;
  top_signatures: { name: string; count: number; severity: Severity }[];
  traffic: Collector["traffic"];
};

// --- Incidents, remediation, reports (Phase 5) ---------------------------------------------

export type PersonRef = { id: string; name: string };

export type Incident = {
  id: string;
  reference: string;
  title: string;
  summary: string;
  severity: Severity;
  status: "open" | "investigating" | "contained" | "resolved" | "closed";
  category: string;
  source: "manual" | "employee_report" | "correlation";
  owner: PersonRef | null;
  reporter: PersonRef | null;
  created_at: string;
  updated_at: string;
  contained_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  closure_reason: string | null;
  resolution_summary: string | null;
  asset_count: number;
  alert_count: number;
  open_tasks: number;
};

export type Task = {
  id: string;
  kind: "remediation" | "containment" | "recovery";
  title: string;
  description: string;
  priority: Severity;
  status: "open" | "in_progress" | "done" | "verified" | "cancelled";
  finding_id: string | null;
  incident_id: string | null;
  incident_reference: string | null;
  asset_id: string | null;
  asset_name: string | null;
  assignee: PersonRef | null;
  due_at: string | null;
  completed_at: string | null;
  verified_at: string | null;
  verification: string | null;
  note: string | null;
  created_at: string;
  overdue: boolean;
};

export type IncidentDetail = Incident & {
  assets: { id: string; name: string; identifier: string; type: string; criticality: string }[];
  alerts: { id: string; title: string; severity: Severity; status: string; asset_name: string; first_seen_at: string }[];
  timeline: { id: string; event_type: string; actor_label: string | null; body: string | null; data: Record<string, unknown>; occurred_at: string }[];
  evidence: { id: string; filename: string; content_type: string; size_bytes: number; sha256: string; description: string | null; created_at: string; uploaded_by_name: string | null }[];
  tasks: Task[];
  can_manage: boolean;
};

export type RemediationSummary = {
  open: number;
  in_progress: number;
  awaiting_verification: number;
  overdue: number;
  completed_30d: number;
  on_time_rate: number | null;
  median_days_to_fix: number | null;
  unassigned_urgent_findings: number;
};

export type ReportItem = {
  id: string;
  report_type: string;
  type_label: string;
  format: "pdf" | "csv";
  title: string;
  period_start: string;
  period_end: string;
  status: string;
  size_bytes: number | null;
  scheduled: boolean;
  created_by_name: string | null;
  created_at: string;
};

export type ReportTypeInfo = { value: string; label: string; csv: boolean };
