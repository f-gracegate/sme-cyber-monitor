"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  CircleAlert,
  Gauge,
  Laptop,
  Plus,
  ScanSearch,
  Server,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useSession, useOrgKey } from "@/components/session";
import {
  Badge,
  ButtonLink,
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  Skeleton,
  StatCard,
  cn,
} from "@/components/ui";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { CATEGORIES, SEVERITIES, SEVERITY_TONE, auditLabel } from "@/lib/labels";
import { AssetIcon } from "@/components/asset-badges";
import { SeverityBadge, severityBarClass } from "@/components/monitoring-ui";
import { TrendChart } from "@/components/trend-chart";
import type { AuditEntry, Overview, Page } from "@/lib/types";

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Good to do",
};

function Recommendations({ data }: { data: Overview }) {
  if (data.recommendations.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<ShieldCheck className="size-5" />}
          title="No recommended actions right now"
          description="You've completed the setup steps we can check today."
        />
      </Card>
    );
  }
  return (
    <Card padded={false}>
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Recommended next actions</h2>
        <p className="text-[13px] text-muted">Most urgent first.</p>
      </div>
      <ul className="divide-y divide-border">
        {data.recommendations.map((r) => (
          <li key={r.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
            <div
              className={cn(
                "flex size-9 shrink-0 items-center justify-center rounded-lg",
                r.severity === "critical"
                  ? "bg-critical-soft text-critical-text"
                  : r.severity === "high"
                    ? "bg-high-soft text-high-text"
                    : r.severity === "medium"
                      ? "bg-warning-soft text-warning-text"
                      : "bg-info-soft text-info-text",
              )}
            >
              {r.severity === "critical" || r.severity === "high" ? (
                <TriangleAlert className="size-4" />
              ) : (
                <CircleAlert className="size-4" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{r.title}</p>
                <Badge tone={SEVERITY_TONE[r.severity]}>{SEVERITY_LABEL[r.severity]}</Badge>
              </div>
              <p className="mt-0.5 text-sm text-muted">{r.description}</p>
            </div>
            <ButtonLink href={r.action_href} variant="secondary" size="sm">
              {r.action_label}
            </ButtonLink>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CategoryBars({ data }: { data: Overview }) {
  const max = Math.max(1, ...Object.values(data.assets_by_category));
  return (
    <Card>
      <CardHeader
        title="Assets by category"
        description={`${data.assets_total} registered`}
        action={
          <Link href="/assets" className="text-[13px] font-medium text-primary-text">
            View all
          </Link>
        }
      />
      {data.assets_total === 0 ? (
        <p className="py-6 text-center text-sm text-muted">No assets registered yet.</p>
      ) : (
        <ul className="space-y-3">
          {CATEGORIES.map((c) => {
            const n = data.assets_by_category[c.value] ?? 0;
            return (
              <li key={c.value}>
                <Link href={`/assets?category=${c.value}`} className="group block">
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-muted group-hover:text-fg">{c.label}</span>
                    <span className="font-medium tabular-nums">{n}</span>
                  </div>
                  <div className="h-2 rounded-full bg-surface-2">
                    <div
                      className="h-2 rounded-full bg-primary"
                      style={{ width: `${(n / max) * 100}%` }}
                    />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function Coverage({ data }: { data: Overview }) {
  const awaiting = data.assets_by_monitoring_status["not_monitored"] ?? 0;
  const authorised = data.assets_authorised;
  const monitoring = data.assets_by_monitoring_status["monitoring"] ?? 0;
  const degraded = data.assets_by_monitoring_status["degraded"] ?? 0;
  const rows = [
    { label: "Actively monitored", value: monitoring, tone: "bg-success" },
    { label: "Monitored with check errors", value: degraded, tone: "bg-high" },
    { label: "Authorised, waiting for a monitoring source", value: authorised - monitoring - degraded, tone: "bg-primary" },
    { label: "Awaiting authorisation", value: awaiting, tone: "bg-warning" },
  ];
  const total = Math.max(1, data.assets_total);
  return (
    <Card>
      <CardHeader
        title="Monitoring coverage"
        description="Which assets are actually protected."
      />
      <div className="mb-4 flex h-3 overflow-hidden rounded-full bg-surface-2">
        {rows.map((r) =>
          r.value > 0 ? (
            <div key={r.label} className={r.tone} style={{ width: `${(r.value / total) * 100}%` }} />
          ) : null,
        )}
      </div>
      <ul className="space-y-2.5 text-sm">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center gap-2.5">
            <span className={cn("size-2.5 rounded-full", r.tone)} aria-hidden />
            <span className="flex-1 text-muted">{r.label}</span>
            <span className="font-medium tabular-nums">{r.value}</span>
          </li>
        ))}
      </ul>
      <p className="mt-4 rounded-lg bg-surface-2 p-3 text-[13px] text-muted">
        Websites and domains are monitored today. Computers, servers and network devices are
        covered once endpoint agents (Phase 3) and network collectors (Phase 4) are added.
      </p>
    </Card>
  );
}

function TeamSecurity({ data }: { data: Overview }) {
  const pct = data.members_total
    ? Math.round((data.members_with_mfa / data.members_total) * 100)
    : 0;
  return (
    <Card>
      <CardHeader
        title="Account security"
        description="Multi-factor authentication across your team."
        action={
          <Link href="/team" className="text-[13px] font-medium text-primary-text">
            Team
          </Link>
        }
      />
      <div className="flex items-end gap-2">
        <p className="text-3xl font-semibold tabular-nums">{pct}%</p>
        <p className="pb-1 text-sm text-muted">
          {data.members_with_mfa} of {data.members_total} members use MFA
        </p>
      </div>
      <div className="mt-3 h-2 rounded-full bg-surface-2">
        <div
          className={cn("h-2 rounded-full", pct === 100 ? "bg-success" : "bg-warning")}
          style={{ width: `${pct}%` }}
        />
      </div>
      {data.privileged_without_mfa > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-[13px] text-critical-text">
          <TriangleAlert className="size-3.5" /> {data.privileged_without_mfa} administrator
          account(s) without MFA
        </p>
      )}
      {data.pending_invitations > 0 && (
        <p className="mt-2 text-[13px] text-muted">
          {data.pending_invitations} invitation(s) waiting to be accepted
        </p>
      )}
    </Card>
  );
}

function RecentActivity() {
  const { can } = useSession();
  const key = useOrgKey("audit", "recent");
  const { data } = useQuery({
    queryKey: key,
    queryFn: () => api<Page<AuditEntry>>("/audit-logs", { query: { page_size: 6 } }),
    enabled: can("audit:read"),
  });
  if (!can("audit:read")) return null;
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Recent activity</h2>
        <Link href="/settings/audit" className="text-[13px] font-medium text-primary-text">
          Audit history
        </Link>
      </div>
      <ul className="divide-y divide-border">
        {(data?.items ?? []).map((e) => (
          <li key={e.id} className="flex items-center gap-3 px-5 py-3 text-sm">
            <Activity className="size-4 shrink-0 text-subtle" />
            <span className="min-w-0 flex-1 truncate">
              <span className="font-medium">{auditLabel(e.action)}</span>
              <span className="text-muted"> · {e.actor_label ?? "System"}</span>
            </span>
            <span className="shrink-0 text-xs text-subtle">{timeAgo(e.created_at)}</span>
          </li>
        ))}
        {data && data.items.length === 0 && (
          <li className="px-5 py-6 text-center text-sm text-muted">No activity yet.</li>
        )}
      </ul>
    </Card>
  );
}

function scoreTone(score: number) {
  return score >= 80 ? "text-success-text" : score >= 50 ? "text-warning-text" : "text-critical-text";
}

function SeverityBars({
  title,
  href,
  counts,
  empty,
}: {
  title: string;
  href: string;
  counts: Record<string, number>;
  empty: string;
}) {
  const rows = SEVERITIES.filter((s) => s.value !== "informational" || counts[s.value]);
  const max = Math.max(1, ...rows.map((r) => counts[r.value] ?? 0));
  const total = rows.reduce((a, r) => a + (counts[r.value] ?? 0), 0);
  return (
    <Card>
      <CardHeader
        title={title}
        action={
          <Link href={href} className="text-[13px] font-medium text-primary-text">
            View all
          </Link>
        }
      />
      {total === 0 ? (
        <p className="py-6 text-center text-sm text-muted">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((r) => {
            const n = counts[r.value] ?? 0;
            return (
              <li key={r.value}>
                <Link href={`${href}?severity=${r.value}`} className="group block">
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-muted group-hover:text-fg">{r.label}</span>
                    <span className="font-medium tabular-nums">{n}</span>
                  </div>
                  <div className="h-2 rounded-full bg-surface-2">
                    <div className={cn("h-2 rounded-full", severityBarClass(r.value))} style={{ width: `${(n / max) * 100}%` }} />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function RecentAlerts({ data }: { data: Overview }) {
  const { can } = useSession();
  if (!can("alerts:read")) return null;
  return (
    <Card padded={false}>
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Recent alerts</h2>
        <Link href="/alerts" className="text-[13px] font-medium text-primary-text">
          All alerts
        </Link>
      </div>
      {data.recent_alerts.length === 0 ? (
        <p className="px-5 py-6 text-center text-sm text-muted">No open alerts.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.recent_alerts.map((a) => (
            <li key={a.id}>
              <Link href={`/alerts/${a.id}`} className="flex items-center gap-3 px-5 py-3 text-sm hover:bg-surface-2/60">
                <span className={cn("size-2 shrink-0 rounded-full", severityBarClass(a.severity))} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{a.title}</span>
                  <span className="block truncate text-xs text-muted">{a.asset_name}</span>
                </span>
                <span className="shrink-0 text-xs text-subtle">{timeAgo(a.last_seen_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function MostExposed({ data }: { data: Overview }) {
  const { can } = useSession();
  if (!can("findings:read") || data.most_exposed_assets.length === 0) return null;
  return (
    <Card padded={false}>
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Most exposed assets</h2>
        <p className="text-[13px] text-muted">Ranked by their most serious open finding.</p>
      </div>
      <ul className="divide-y divide-border">
        {data.most_exposed_assets.map((a) => (
          <li key={a.id}>
            <Link href={`/assets/${a.id}`} className="flex items-center gap-3 px-5 py-3 text-sm hover:bg-surface-2/60">
              <AssetIcon type={a.type} className="size-4 shrink-0 text-subtle" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{a.name}</span>
                <span className="block truncate text-xs text-muted">
                  {a.open_findings} open finding{a.open_findings === 1 ? "" : "s"}
                </span>
              </span>
              <SeverityBadge severity={a.highest_severity} />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function OverviewPage() {
  const { can, membership } = useSession();
  const key = useOrgKey("overview");
  const { data, isPending } = useQuery({
    queryKey: key,
    queryFn: () => api<Overview>("/overview"),
  });

  const sev = data?.findings_open_by_severity;
  const urgent = sev ? sev.critical + sev.high : 0;
  const totalOpen = sev ? Object.values(sev).reduce((a, b) => a + b, 0) : 0;
  const openAlerts = data ? Object.values(data.alerts_open_by_severity).reduce((a, b) => a + b, 0) : 0;

  return (
    <>
      <PageHeader
        title="Security overview"
        description={membership ? `${membership.organisation_name} · ${membership.role_label}` : undefined}
        actions={
          can("assets:write") && (
            <ButtonLink href="/assets?new=1">
              <Plus className="size-4" /> Add asset
            </ButtonLink>
          )
        }
      />

      {isPending || !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label="Security posture score"
              value={
                data.posture_score === null ? (
                  "—"
                ) : (
                  <span className={scoreTone(data.posture_score)}>
                    {data.posture_score}
                    <span className="text-base font-normal text-subtle"> / 100</span>
                  </span>
                )
              }
              hint={
                data.posture_score === null
                  ? "Needs monitoring data"
                  : `${data.monitored_assets} of ${data.monitorable_assets} websites/domains monitored`
              }
              icon={<Gauge className="size-4" />}
              tone="primary"
            />
            <StatCard
              label="Registered assets"
              value={data.assets_total}
              hint={`${data.assets_authorised} authorised · ${data.critical_assets} critical`}
              icon={<Server className="size-4" />}
              tone="info"
            />
            <Link href="/findings?severity=critical&severity=high" className="block rounded-[var(--radius-card)] focus-visible:outline-2">
              <StatCard
                label="Critical & high findings"
                value={urgent}
                hint={`${totalOpen} open finding${totalOpen === 1 ? "" : "s"} in total`}
                icon={<ScanSearch className="size-4" />}
                tone="critical"
              />
            </Link>
            <Link href="/alerts" className="block rounded-[var(--radius-card)] focus-visible:outline-2">
              <StatCard
                label="Open alerts"
                value={openAlerts}
                hint={openAlerts ? "Waiting for someone to act" : "Nothing needs attention"}
                icon={<Bell className="size-4" />}
                tone="high"
              />
            </Link>
            <StatCard
              label="Online endpoints"
              value="—"
              hint="Endpoint agents arrive in Phase 3"
              icon={<Laptop className="size-4" />}
              tone="success"
            />
          </div>

          <p className="-mt-2 text-[13px] text-muted">{data.posture_note}</p>

          <div className="grid gap-6 xl:grid-cols-3">
            <div className="space-y-6 xl:col-span-2">
              <Recommendations data={data} />
              <Card>
                <CardHeader title="Security posture over time" description="Daily score, last 30 days." />
                <TrendChart points={data.trend} />
              </Card>
              <div className="grid gap-6 md:grid-cols-2">
                <SeverityBars
                  title="Open findings by severity"
                  href="/findings"
                  counts={data.findings_open_by_severity}
                  empty="No open findings."
                />
                <SeverityBars
                  title="Open alerts by severity"
                  href="/alerts"
                  counts={data.alerts_open_by_severity}
                  empty="No open alerts."
                />
              </div>
              <div className="grid gap-6 md:grid-cols-2">
                <CategoryBars data={data} />
                <Coverage data={data} />
              </div>
            </div>
            <div className="space-y-6">
              <RecentAlerts data={data} />
              <MostExposed data={data} />
              <TeamSecurity data={data} />
              <RecentActivity />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
