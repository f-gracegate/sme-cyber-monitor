// Plain-language labels. Business owners should never have to decode internal identifiers.

export const ASSET_TYPES: { value: string; label: string; category: string }[] = [
  { value: "website", label: "Website", category: "websites_domains" },
  { value: "domain", label: "Domain", category: "websites_domains" },
  { value: "workstation", label: "Workstation", category: "workstations_laptops" },
  { value: "laptop", label: "Laptop", category: "workstations_laptops" },
  { value: "server", label: "Server", category: "servers" },
  { value: "firewall", label: "Firewall", category: "firewalls_routers" },
  { value: "router", label: "Router", category: "firewalls_routers" },
  { value: "switch", label: "Switch", category: "network_devices" },
  { value: "network_device", label: "Other network device", category: "network_devices" },
  { value: "cloud_account", label: "Cloud account", category: "cloud" },
  { value: "cloud_service", label: "Cloud service", category: "cloud" },
];

export const assetTypeLabel = (t: string) =>
  ASSET_TYPES.find((a) => a.value === t)?.label ?? t;

export const CATEGORIES: { value: string; label: string }[] = [
  { value: "websites_domains", label: "Websites & domains" },
  { value: "workstations_laptops", label: "Workstations & laptops" },
  { value: "servers", label: "Servers" },
  { value: "firewalls_routers", label: "Firewalls & routers" },
  { value: "network_devices", label: "Switches & network devices" },
  { value: "cloud", label: "Cloud accounts & services" },
];

export const categoryLabel = (c: string) => CATEGORIES.find((x) => x.value === c)?.label ?? c;

export const IDENTIFIER_HINTS: Record<string, { label: string; placeholder: string }> = {
  website: { label: "Website address", placeholder: "https://www.yourbusiness.com.gh" },
  domain: { label: "Domain name", placeholder: "yourbusiness.com.gh" },
  workstation: { label: "Computer name or serial number", placeholder: "FRONTDESK-01" },
  laptop: { label: "Computer name or serial number", placeholder: "ACC-LT-02" },
  server: { label: "Hostname or IP address", placeholder: "fs01.office.local" },
  firewall: { label: "Management IP or hostname", placeholder: "192.168.1.1" },
  router: { label: "Management IP or hostname", placeholder: "192.168.1.1" },
  switch: { label: "Management IP or hostname", placeholder: "192.168.1.2" },
  network_device: { label: "IP address, hostname or serial", placeholder: "10.0.0.20" },
  cloud_account: { label: "Account ID or name", placeholder: "Microsoft 365 tenant" },
  cloud_service: { label: "Service name or URL", placeholder: "Google Workspace" },
};

export const CRITICALITY = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

export const MONITORING_STATUS: Record<string, { label: string; tone: Tone; help: string }> = {
  not_monitored: {
    label: "Awaiting authorisation",
    tone: "warning",
    help: "Prove you own or may monitor this asset before monitoring can start.",
  },
  authorised: {
    label: "Authorised",
    tone: "info",
    help: "Ownership confirmed. Monitoring starts when a monitoring source is connected.",
  },
  monitoring: { label: "Monitoring", tone: "success", help: "Actively monitored." },
  degraded: { label: "Degraded", tone: "high", help: "Some checks are failing or missing." },
  paused: { label: "Paused", tone: "neutral", help: "Monitoring is paused." },
};

export const VERIFICATION_METHODS: Record<string, string> = {
  dns_txt: "DNS TXT record",
  http_file: "Verification file on website",
  attestation: "Administrator confirmation",
  agent: "Monitoring agent installed on the device",
};

export const INDUSTRIES = [
  { value: "retail", label: "Retail" },
  { value: "ecommerce", label: "Ecommerce" },
  { value: "hospitality", label: "Hotels & hospitality" },
  { value: "education", label: "Schools & education" },
  { value: "healthcare", label: "Clinics & healthcare" },
  { value: "professional_services", label: "Professional services (legal, accounting)" },
  { value: "finance", label: "Financial services" },
  { value: "technology", label: "Technology" },
  { value: "manufacturing", label: "Manufacturing" },
  { value: "logistics", label: "Logistics & distribution" },
  { value: "ngo", label: "NGO / non-profit" },
  { value: "other", label: "Other" },
];

export const SIZES = ["1-10", "11-50", "51-200", "201-500", "500+"];

export type Tone = "neutral" | "info" | "success" | "warning" | "high" | "critical" | "primary";

export const SEVERITY_TONE: Record<string, Tone> = {
  critical: "critical",
  high: "high",
  medium: "warning",
  low: "info",
  informational: "neutral",
};

export const AUDIT_ACTIONS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in attempt",
  "auth.mfa_failed": "Failed MFA code",
  "auth.logout": "Signed out",
  "auth.refresh_reuse_detected": "Session ended: token reuse detected",
  "user.registered": "Account created",
  "user.seeded": "Administrator account created",
  "user.password_changed": "Password changed",
  "user.password_reset_requested": "Password reset requested",
  "user.password_reset": "Password reset",
  "user.mfa_enabled": "MFA turned on",
  "user.mfa_disabled": "MFA turned off",
  "organisation.created": "Organisation created",
  "organisation.updated": "Organisation settings changed",
  "member.invited": "Member invited",
  "member.invitation_revoked": "Invitation revoked",
  "member.joined": "Member joined",
  "member.updated": "Member updated",
  "member.removed": "Member removed",
  "department.created": "Department created",
  "department.deleted": "Department deleted",
  "asset.created": "Asset registered",
  "asset.updated": "Asset updated",
  "asset.archived": "Asset archived",
  "asset.restored": "Asset restored",
  "asset.verification_started": "Verification started",
  "asset.verification_failed": "Verification check failed",
  "asset.authorised": "Asset authorised",
};

export const auditLabel = (a: string) => AUDIT_ACTIONS[a] ?? a;

// --- Monitoring -----------------------------------------------------------------------------

export const CHECK_TYPES: Record<string, { label: string; description: string }> = {
  uptime: {
    label: "Uptime",
    description: "Is the website answering, and how fast?",
  },
  tls: {
    label: "TLS certificate",
    description: "Certificate validity, expiry and secure protocol versions.",
  },
  security_headers: {
    label: "Security headers",
    description: "Browser protections such as HSTS, CSP and secure cookies.",
  },
  dns: {
    label: "DNS",
    description: "Nameservers, records and unexpected changes.",
  },
  email_security: {
    label: "Email security",
    description: "SPF and DMARC protection against email spoofing.",
  },
  agent_heartbeat: {
    label: "Agent connection",
    description: "Is the device's monitoring agent checking in?",
  },
  endpoint_health: {
    label: "Device health",
    description: "Antivirus, firewall, encryption, updates and disk space.",
  },
  device_availability: {
    label: "Reachability",
    description: "Can the on-site collector reach this device?",
  },
  collector_health: {
    label: "Collector health",
    description: "Is the collector keeping up with the logs it receives?",
  },
};

export const AGENT_CHECK_TYPES = new Set([
  "agent_heartbeat",
  "endpoint_health",
  "device_availability",
  "collector_health",
]);

export const EVENT_TYPES: Record<string, string> = {
  "authentication.failure": "Failed sign-in",
  "authentication.success": "Successful sign-in",
  "malware.detected": "Malware detected",
  "protection.disabled": "Protection disabled",
  "account.privileged_created": "Admin account change",
  "log.cleared": "Log cleared",
  "process.suspicious": "Suspicious process",
  "removable_media.connected": "Removable storage",
  "file_integrity.changed": "File changed",
  generic: "Other event",
  "network.firewall_deny": "Blocked connections",
  "network.config_change": "Configuration change",
  "network.admin_login_failure": "Failed admin login",
  "network.admin_login_success": "Admin login",
  "network.vpn_login": "VPN login",
  "network.ids_alert": "Intrusion detection",
  "network.zeek_notice": "Zeek notice",
};

export const NETWORK_EVENT_TYPES = Object.keys(EVENT_TYPES).filter((k) => k.startsWith("network."));
export const ENDPOINT_EVENT_TYPES = Object.keys(EVENT_TYPES).filter((k) => !k.startsWith("network."));

export const AGENT_SOURCE: Record<string, string> = {
  smecm_agent: "SMECM agent",
  wazuh: "Wazuh",
  collector: "Network collector",
};

export const CAPABILITIES: Record<string, string> = {
  syslog_udp: "Syslog (UDP)",
  syslog_tcp: "Syslog (TCP)",
  suricata: "Suricata IDS",
  zeek: "Zeek",
  probe: "Reachability checks",
};

export const checkTypeLabel = (t: string) => CHECK_TYPES[t]?.label ?? t;

export const CHECK_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending: { label: "Waiting for first run", tone: "neutral" },
  ok: { label: "Passing", tone: "success" },
  warning: { label: "Issues found", tone: "warning" },
  failing: { label: "Failing", tone: "critical" },
  error: { label: "Couldn't check", tone: "high" },
  disabled: { label: "Turned off", tone: "neutral" },
};

export const INTERVALS = [
  { value: 5, label: "Every 5 min" },
  { value: 15, label: "Every 15 min" },
  { value: 30, label: "Every 30 min" },
  { value: 60, label: "Hourly" },
  { value: 180, label: "Every 3 hours" },
  { value: 360, label: "Every 6 hours" },
  { value: 720, label: "Every 12 hours" },
  { value: 1440, label: "Daily" },
];

export const SEVERITIES = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "informational", label: "Informational" },
] as const;

export const severityLabel = (s: string) => SEVERITIES.find((x) => x.value === s)?.label ?? s;

export const ALERT_STATUS: Record<string, { label: string; tone: Tone }> = {
  new: { label: "New", tone: "critical" },
  acknowledged: { label: "Acknowledged", tone: "warning" },
  investigating: { label: "Investigating", tone: "primary" },
  resolved: { label: "Resolved", tone: "success" },
};

export const FINDING_STATUS: Record<string, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "warning" },
  accepted_risk: { label: "Risk accepted", tone: "neutral" },
  resolved: { label: "Resolved", tone: "success" },
};

Object.assign(AUDIT_ACTIONS, {
  "monitoring.check_created": "Monitoring check added",
  "monitoring.check_updated": "Monitoring check changed",
  "finding.updated": "Finding status changed",
  "alert.updated": "Alert status changed",
  "endpoint.enrolled": "Device enrolled",
  "endpoint.revoked": "Device agent revoked",
  "endpoint.token_created": "Enrolment token created",
  "endpoint.token_revoked": "Enrolment token revoked",
  "integration.key_created": "Integration key created",
  "integration.key_revoked": "Integration key revoked",
  "network.collector_enrolled": "Network collector enrolled",
});
