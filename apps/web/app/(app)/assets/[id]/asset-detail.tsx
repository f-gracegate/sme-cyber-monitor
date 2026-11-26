"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Archive,
  ArrowLeft,
  CircleCheck,
  Clock,
  Pencil,
  RotateCcw,
  ScanSearch,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  AssetIcon,
  CriticalityBadge,
  MonitoringBadge,
  RiskBadge,
} from "@/components/asset-badges";
import { AssetFormDialog } from "@/components/asset-form";
import { CopyField } from "@/components/copy-field";
import { Dialog } from "@/components/dialog";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Field,
  PageHeader,
  Skeleton,
  Textarea,
  cn,
} from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import {
  MONITORING_STATUS,
  VERIFICATION_METHODS,
  assetTypeLabel,
  auditLabel,
  categoryLabel,
} from "@/lib/labels";
import type { AssetDetail, AuditEntry, Page } from "@/lib/types";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "monitoring", label: "Monitoring history" },
  { id: "findings", label: "Security findings" },
  { id: "events", label: "Events" },
  { id: "configuration", label: "Configuration" },
  { id: "activity", label: "Activity & audit" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium tracking-wide text-subtle uppercase">{label}</dt>
      <dd className="mt-1 text-sm text-fg">{children}</dd>
    </div>
  );
}

function VerificationCard({ asset }: { asset: AssetDetail }) {
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const external = asset.type === "website" || asset.type === "domain";
  const [method, setMethod] = useState<string>(asset.verification_methods[0]);
  const [statement, setStatement] = useState("");
  const [attestOpen, setAttestOpen] = useState(false);
  const auth = asset.authorisation;
  const canVerify = can("assets:verify") && asset.status === "active";

  const onUpdated = (data: AssetDetail) => {
    queryClient.setQueryData([...orgKey, "asset", asset.id], data);
    queryClient.invalidateQueries({ queryKey: orgKey });
  };

  const start = useMutation({
    mutationFn: (body: { method: string; statement?: string }) =>
      api<AssetDetail>(`/assets/${asset.id}/verification`, { method: "POST", body }),
    onSuccess: (data) => {
      onUpdated(data);
      setAttestOpen(false);
      if (data.monitoring_status === "authorised") toast("success", "Asset authorised.");
    },
  });
  const check = useMutation({
    mutationFn: () => api<AssetDetail>(`/assets/${asset.id}/verify`, { method: "POST" }),
    onSuccess: (data) => {
      onUpdated(data);
      toast(
        data.authorisation?.status === "verified" ? "success" : "error",
        data.authorisation?.status === "verified"
          ? "Ownership verified."
          : "Verification didn't pass yet.",
      );
    },
  });

  if (auth?.status === "verified") {
    return (
      <Card>
        <CardHeader title="Authorisation" />
        <Callout
          tone="success"
          icon={<ShieldCheck className="size-4" />}
          title="This asset is authorised for monitoring"
        >
          {VERIFICATION_METHODS[auth.method]} · {formatDateTime(auth.verified_at)}
          {auth.method === "attestation" && typeof auth.evidence.statement === "string" && (
            <p className="mt-2 italic">&ldquo;{auth.evidence.statement}&rdquo;</p>
          )}
        </Callout>
        <p className="mt-3 text-[13px] text-muted">
          {MONITORING_STATUS[asset.monitoring_status]?.help}
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Authorisation"
        description={
          external
            ? "Before we monitor a website or domain, you prove you control it. This stops anyone from pointing our scanners at systems they don't own."
            : "Confirm your organisation owns this device or is authorised to monitor it. Agent enrolment will add technical proof later."
        }
      />
      {(start.isError || check.isError) && (
        <div className="mb-4">
          <Callout tone="critical">{errorMessage(start.error ?? check.error)}</Callout>
        </div>
      )}

      {auth && auth.method !== "attestation" && asset.instructions ? (
        <div className="space-y-4">
          {auth.status === "failed" && auth.failure_reason && (
            <Callout tone="warning" title="Not verified yet">
              {auth.failure_reason}
              {auth.last_attempt_at && (
                <span className="block text-xs opacity-80">
                  Last checked {timeAgo(auth.last_attempt_at)}
                </span>
              )}
            </Callout>
          )}
          <p className="text-sm text-fg">{asset.instructions.summary}</p>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
            {asset.instructions.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          {asset.instructions.record_name && (
            <div className="grid gap-3">
              <CopyField label="Record type" value="TXT" />
              <CopyField label="Name / host" value={asset.instructions.record_name} />
              <CopyField label="Value" value={asset.instructions.record_value ?? ""} />
            </div>
          )}
          {asset.instructions.file_url && (
            <div className="grid gap-3">
              <CopyField label="File address" value={asset.instructions.file_url} />
              <CopyField label="File contents" value={asset.instructions.file_contents ?? ""} />
            </div>
          )}
          {canVerify && (
            <div className="flex flex-wrap gap-2 pt-1">
              <Button loading={check.isPending} onClick={() => check.mutate()}>
                <ScanSearch className="size-4" /> Check verification
              </Button>
              <Button
                variant="ghost"
                onClick={() =>
                  start.mutate({ method: auth.method === "dns_txt" ? "http_file" : "dns_txt" })
                }
              >
                Use {auth.method === "dns_txt" ? "a verification file" : "a DNS record"} instead
              </Button>
            </div>
          )}
        </div>
      ) : !canVerify ? (
        <Callout tone="warning" icon={<ShieldQuestion className="size-4" />}>
          Awaiting authorisation by an administrator.
        </Callout>
      ) : external ? (
        <div className="space-y-3">
          <fieldset className="grid gap-2 sm:grid-cols-2">
            <legend className="sr-only">Verification method</legend>
            {asset.verification_methods.map((m) => (
              <label
                key={m}
                className={cn(
                  "cursor-pointer rounded-[var(--radius-control)] border p-3 text-sm",
                  method === m ? "border-primary bg-primary-soft" : "border-border-strong hover:bg-surface-2",
                )}
              >
                <input
                  type="radio"
                  name="method"
                  value={m}
                  checked={method === m}
                  onChange={() => setMethod(m)}
                  className="sr-only"
                />
                <span className="block font-medium">{VERIFICATION_METHODS[m]}</span>
                <span className="mt-0.5 block text-[13px] text-muted">
                  {m === "dns_txt"
                    ? "Best if you manage your domain's DNS."
                    : "Best if you can upload files to your website."}
                </span>
              </label>
            ))}
          </fieldset>
          <Button loading={start.isPending} onClick={() => start.mutate({ method })}>
            Get verification instructions
          </Button>
        </div>
      ) : (
        <>
          <Button onClick={() => setAttestOpen(true)}>
            <CircleCheck className="size-4" /> Confirm authorisation
          </Button>
          <Dialog
            open={attestOpen}
            onClose={() => setAttestOpen(false)}
            title="Confirm authorisation"
            description="This confirmation is recorded in the audit history with your name."
            footer={
              <>
                <Button variant="secondary" onClick={() => setAttestOpen(false)}>
                  Cancel
                </Button>
                <Button
                  loading={start.isPending}
                  disabled={!statement.trim()}
                  onClick={() => start.mutate({ method: "attestation", statement })}
                >
                  Confirm
                </Button>
              </>
            }
          >
            <Field
              label="Why is your organisation authorised to monitor this asset?"
              htmlFor="statement"
              hint="For example: “Company-owned laptop issued to our accountant.”"
            >
              <Textarea
                id="statement"
                value={statement}
                onChange={(e) => setStatement(e.target.value)}
                rows={3}
                autoFocus
              />
            </Field>
          </Dialog>
        </>
      )}
    </Card>
  );
}

function ActivityTab({ assetId }: { assetId: string }) {
  const { data, isPending } = useQuery({
    queryKey: useOrgKey("asset", assetId, "activity"),
    queryFn: () => api<Page<AuditEntry>>(`/assets/${assetId}/activity`, { query: { page_size: 50 } }),
  });
  if (isPending) return <Skeleton className="h-40" />;
  if (!data?.items.length) return <EmptyState title="No activity recorded" />;
  return (
    <Card padded={false}>
      <ol className="divide-y divide-border">
        {data.items.map((e) => (
          <li key={e.id} className="flex gap-3 px-5 py-3.5">
            <Activity className="mt-0.5 size-4 shrink-0 text-subtle" />
            <div className="min-w-0 flex-1 text-sm">
              <p>
                <span className="font-medium">{auditLabel(e.action)}</span>
                <span className="text-muted"> by {e.actor_label ?? "System"}</span>
              </p>
              {"changes" in e.details && e.details.changes && typeof e.details.changes === "object" ? (
                <ul className="mt-1 space-y-0.5 text-[13px] text-muted">
                  {Object.entries(e.details.changes as Record<string, { from: string | null; to: string | null }>).map(
                    ([field, c]) => (
                      <li key={field}>
                        {field.replace(/_/g, " ")}: <s>{c.from ?? "—"}</s> → {c.to ?? "—"}
                      </li>
                    ),
                  )}
                </ul>
              ) : typeof e.details.detail === "string" ? (
                <p className="mt-0.5 text-[13px] text-muted">{e.details.detail}</p>
              ) : null}
            </div>
            <time className="shrink-0 text-xs text-subtle" dateTime={e.created_at} title={formatDateTime(e.created_at)}>
              {timeAgo(e.created_at)}
            </time>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function AssetDetailView() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [tab, setTab] = useState<TabId>("overview");
  const [editing, setEditing] = useState(false);

  const { data: asset, isPending, error } = useQuery({
    queryKey: [...orgKey, "asset", id],
    queryFn: () => api<AssetDetail>(`/assets/${id}`),
  });

  const toggleArchive = useMutation({
    mutationFn: () =>
      api<AssetDetail>(`/assets/${id}/${asset?.status === "archived" ? "restore" : "archive"}`, {
        method: "POST",
      }),
    onSuccess: (data) => {
      queryClient.setQueryData([...orgKey, "asset", id], data);
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", data.status === "archived" ? "Asset archived." : "Asset restored.");
    },
    onError: (err) => toast("error", errorMessage(err)),
  });

  const back = (
    <Link href="/assets" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
      <ArrowLeft className="size-4" /> Assets
    </Link>
  );

  if (isPending) {
    return (
      <div className="space-y-4">
        {back}
        <Skeleton className="h-16 w-1/2" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (error || !asset) {
    return (
      <>
        {back}
        <Card>
          <EmptyState
            title={error instanceof ApiError && error.status === 404 ? "Asset not found" : "Couldn't load this asset"}
            description={errorMessage(error)}
          />
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        back={back}
        title={
          <span className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-xl bg-primary-soft text-primary-text">
              <AssetIcon type={asset.type} className="size-5" />
            </span>
            <span className="min-w-0">
              <span className="block truncate">{asset.name}</span>
              <span className="block truncate font-mono text-sm font-normal text-subtle">{asset.identifier}</span>
            </span>
          </span>
        }
        actions={
          can("assets:write") && (
            <>
              {asset.status === "active" && (
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  <Pencil className="size-4" /> Edit
                </Button>
              )}
              <Button
                variant="secondary"
                loading={toggleArchive.isPending}
                onClick={() => toggleArchive.mutate()}
              >
                {asset.status === "archived" ? (
                  <>
                    <RotateCcw className="size-4" /> Restore
                  </>
                ) : (
                  <>
                    <Archive className="size-4" /> Archive
                  </>
                )}
              </Button>
            </>
          )
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <MonitoringBadge status={asset.monitoring_status} />
        <CriticalityBadge level={asset.criticality} />
        <Badge>{assetTypeLabel(asset.type)}</Badge>
        {asset.status === "archived" && <Badge tone="warning">Archived</Badge>}
      </div>

      <div className="mb-6 overflow-x-auto border-b border-border" role="tablist">
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2.5 text-sm whitespace-nowrap",
                tab === t.id
                  ? "border-primary font-medium text-primary-text"
                  : "border-transparent text-muted hover:text-fg",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "overview" && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <Card>
            <CardHeader title="Details" />
            <dl className="grid gap-5 sm:grid-cols-2">
              <Detail label="Category">{categoryLabel(asset.category)}</Detail>
              <Detail label="Type">{assetTypeLabel(asset.type)}</Detail>
              <Detail label="Department">{asset.department_name ?? "—"}</Detail>
              <Detail label="Owner">{asset.owner_name ?? "—"}</Detail>
              <Detail label="OS / technology">{asset.technology ?? "—"}</Detail>
              <Detail label="Location">{asset.location ?? "—"}</Detail>
              <Detail label="Risk level">
                <RiskBadge level={asset.risk_level} />
              </Detail>
              <Detail label="Registered">{formatDateTime(asset.created_at)}</Detail>
              <Detail label="Last seen">{timeAgo(asset.last_seen_at)}</Detail>
              <Detail label="Last successful check">{timeAgo(asset.last_successful_check_at)}</Detail>
              {asset.notes && (
                <div className="sm:col-span-2">
                  <Detail label="Notes">
                    <span className="whitespace-pre-wrap">{asset.notes}</span>
                  </Detail>
                </div>
              )}
            </dl>
          </Card>
          <VerificationCard asset={asset} />
        </div>
      )}

      {tab === "monitoring" && (
        <Card>
          <EmptyState
            icon={<Clock className="size-5" />}
            title="No monitoring checks have run yet"
            description={
              asset.type === "website" || asset.type === "domain"
                ? "Uptime, DNS, TLS certificate and security header checks run here once website monitoring is switched on (next development phase)."
                : "Health and security checks appear here once an endpoint agent or network collector reports for this asset."
            }
          />
        </Card>
      )}
      {tab === "findings" && (
        <Card>
          <EmptyState
            icon={<ScanSearch className="size-5" />}
            title="No findings"
            description="Vulnerabilities and misconfigurations detected for this asset will be listed here with what to do next. No findings yet means no checks have run, not that the asset is safe."
          />
        </Card>
      )}
      {tab === "events" && (
        <Card>
          <EmptyState
            icon={<Activity className="size-5" />}
            title="No security events"
            description="Login attempts, process alerts and network events from agents and collectors will appear here."
          />
        </Card>
      )}
      {tab === "configuration" && (
        <Card>
          <CardHeader
            title="Monitoring configuration"
            description="Check schedules and monitoring profiles become configurable as each monitoring module is added."
          />
          <dl className="grid gap-5 sm:grid-cols-3">
            <Detail label="Monitoring status">
              <MonitoringBadge status={asset.monitoring_status} />
            </Detail>
            <Detail label="Authorisation method">
              {asset.authorisation ? VERIFICATION_METHODS[asset.authorisation.method] : "—"}
            </Detail>
            <Detail label="Collection method">
              {asset.type === "website" || asset.type === "domain"
                ? "Cloud monitoring worker"
                : ["firewall", "router", "switch", "network_device"].includes(asset.type)
                  ? "On-premises network collector"
                  : asset.type.startsWith("cloud")
                    ? "Cloud provider integration"
                    : "Endpoint agent"}
            </Detail>
          </dl>
        </Card>
      )}
      {tab === "activity" && <ActivityTab assetId={asset.id} />}

      {editing && <AssetFormDialog open asset={asset} onClose={() => setEditing(false)} />}
    </>
  );
}
