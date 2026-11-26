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

export type Overview = {
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
