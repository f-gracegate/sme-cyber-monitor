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
  asset_limit: number | null;
  member_limit: number | null;
  features: string[];
};

export type Subscription = {
  plan: Plan;
  status: string;
  billing_period: string;
  current_period_end: string | null;
  assets_used: number;
  members_used: number;
  available_plans: Plan[];
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
