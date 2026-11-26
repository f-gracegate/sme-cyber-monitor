"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  CircleAlert,
  Gauge,
  Laptop,
  Plus,
  ScanSearch,
  Server,
  ShieldCheck,
  Siren,
  TriangleAlert,
  Users,
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
import { CATEGORIES, SEVERITY_TONE, auditLabel } from "@/lib/labels";
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
  const rows = [
    { label: "Actively monitored", value: monitoring, tone: "bg-success" },
    { label: "Authorised, waiting for a monitoring source", value: authorised - monitoring, tone: "bg-primary" },
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
        Website, endpoint and network monitoring are being added in the next development phases.
        Coverage gaps are shown here instead of being hidden in the score.
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

export default function OverviewPage() {
  const { can, membership } = useSession();
  const key = useOrgKey("overview");
  const { data, isPending } = useQuery({
    queryKey: key,
    queryFn: () => api<Overview>("/overview"),
  });

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
              value={data.posture_score ?? "—"}
              hint="Needs monitoring data"
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
            <StatCard
              label="Critical & high findings"
              value="—"
              hint="Appear once monitoring starts"
              icon={<ScanSearch className="size-4" />}
              tone="critical"
            />
            <StatCard
              label="Open incidents"
              value="—"
              hint="Incident management coming soon"
              icon={<Siren className="size-4" />}
              tone="high"
            />
            <StatCard
              label="Online endpoints"
              value="—"
              hint="No endpoint agents installed"
              icon={<Laptop className="size-4" />}
              tone="success"
            />
          </div>

          <p className="-mt-2 text-[13px] text-muted">{data.posture_note}</p>

          <div className="grid gap-6 xl:grid-cols-3">
            <div className="space-y-6 xl:col-span-2">
              <Recommendations data={data} />
              <div className="grid gap-6 md:grid-cols-2">
                <CategoryBars data={data} />
                <Coverage data={data} />
              </div>
            </div>
            <div className="space-y-6">
              <TeamSecurity data={data} />
              <RecentActivity />
              <Card>
                <div className="flex items-start gap-3">
                  <Users className="mt-0.5 size-5 text-subtle" />
                  <div>
                    <p className="text-sm font-medium">What happens next</p>
                    <p className="mt-1 text-[13px] text-muted">
                      Register and authorise your assets now. As monitoring modules switch on,
                      findings and alerts will appear here automatically.
                    </p>
                    <Link
                      href="/monitoring"
                      className="mt-2 inline-flex items-center gap-1 text-[13px] font-medium text-primary-text"
                    >
                      Monitoring roadmap <ArrowRight className="size-3.5" />
                    </Link>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
