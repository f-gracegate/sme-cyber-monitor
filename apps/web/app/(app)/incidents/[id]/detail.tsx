"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bell,
  CircleCheck,
  Download,
  FileUp,
  Lock,
  MessageSquare,
  Paperclip,
  Plus,
  RotateCcw,
  Search,
  Server,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState, type ReactNode } from "react";
import { AssetIcon } from "@/components/asset-badges";
import { Dialog } from "@/components/dialog";
import { AssigneeSelect, IncidentStatusBadge, TaskDialog, TaskRow } from "@/components/incident-ui";
import { AlertStatusBadge, SeverityBadge } from "@/components/monitoring-ui";
import { useToast } from "@/components/providers";
import { useOrgKey } from "@/components/session";
import {
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Textarea,
  cn,
} from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import {
  CLOSURE_REASONS,
  INCIDENT_CATEGORIES,
  INCIDENT_SOURCE,
  SEVERITIES,
  categoryName,
} from "@/lib/labels";
import type { Asset, IncidentDetail, Page } from "@/lib/types";

const EVENT_ICON: Record<string, ReactNode> = {
  note: <MessageSquare className="size-3.5" />,
  evidence_added: <Paperclip className="size-3.5" />,
  alert_linked: <Bell className="size-3.5" />,
  asset_linked: <Server className="size-3.5" />,
  task_added: <Wrench className="size-3.5" />,
  task_updated: <Wrench className="size-3.5" />,
  closed: <Lock className="size-3.5" />,
  reopened: <RotateCcw className="size-3.5" />,
};

const ACCEPTED = ".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.log,.csv,.json,.eml,.msg,.pcap,.pcapng,.zip";

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function Detail() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const key = [...orgKey, "incident", id];
  const [closing, setClosing] = useState(false);
  const [addingTask, setAddingTask] = useState(false);
  const [addingAsset, setAddingAsset] = useState(false);

  const { data: inc, isPending, error } = useQuery({
    queryKey: key,
    queryFn: () => api<IncidentDetail>(`/incidents/${id}`),
    refetchInterval: 30_000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: orgKey });
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/incidents/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      refresh();
      setClosing(false);
      toast("success", "Incident updated.");
    },
    onError: (e) => toast("error", errorMessage(e)),
  });

  const back = (
    <Link href="/incidents" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
      <ArrowLeft className="size-4" /> Incidents
    </Link>
  );
  if (isPending) return <Skeleton className="h-96" />;
  if (error || !inc) {
    return (
      <>
        {back}
        <Card>
          <EmptyState title="Incident not found" description={errorMessage(error)} />
        </Card>
      </>
    );
  }

  const manage = inc.can_manage;
  const active = !["resolved", "closed"].includes(inc.status);
  const step = (status: string) => update.isPending && update.variables?.status === status;

  return (
    <>
      <PageHeader
        back={back}
        title={inc.title}
        actions={
          manage && (
            <>
              {inc.status === "open" && (
                <Button variant="secondary" loading={step("investigating")} onClick={() => update.mutate({ status: "investigating" })}>
                  <Search className="size-4" /> Start investigating
                </Button>
              )}
              {(inc.status === "open" || inc.status === "investigating") && (
                <Button variant="secondary" loading={step("contained")} onClick={() => update.mutate({ status: "contained" })}>
                  <ShieldCheck className="size-4" /> Mark contained
                </Button>
              )}
              {active && (
                <Button loading={step("resolved")} onClick={() => update.mutate({ status: "resolved" })}>
                  <CircleCheck className="size-4" /> Resolve
                </Button>
              )}
              {inc.status === "resolved" && (
                <Button onClick={() => setClosing(true)}>
                  <Lock className="size-4" /> Close
                </Button>
              )}
              {!active && (
                <Button variant="secondary" loading={step("investigating")} onClick={() => update.mutate({ status: "investigating" })}>
                  <RotateCcw className="size-4" /> Reopen
                </Button>
              )}
            </>
          )
        }
      />
      <div className="mb-5 flex flex-wrap items-center gap-2 text-sm text-muted">
        <span className="font-mono text-[13px]">{inc.reference}</span>
        <SeverityBadge severity={inc.severity} />
        <IncidentStatusBadge status={inc.status} />
        <span>{categoryName(inc.category)}</span>
        <span>· opened {formatDateTime(inc.created_at)}</span>
        <span>
          ·{" "}
          {inc.reporter
            ? `${inc.source === "employee_report" ? "Reported" : "Opened"} by ${inc.reporter.name}`
            : INCIDENT_SOURCE[inc.source]}
        </span>
      </div>

      {inc.status === "closed" && (
        <div className="mb-5">
          <Callout tone="neutral" title={`Closed — ${CLOSURE_REASONS.find((r) => r.value === inc.closure_reason)?.label ?? inc.closure_reason}`}>
            {formatDateTime(inc.closed_at)}
            {inc.resolution_summary && <span className="mt-1 block whitespace-pre-line">{inc.resolution_summary}</span>}
          </Callout>
        </div>
      )}
      {!manage && (
        <div className="mb-5">
          <Callout tone="info" title="Your security team has this report">
            You can add more information or attach screenshots below. You&rsquo;ll see updates here as they work on it.
          </Callout>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader title="What happened" />
            {inc.summary ? (
              <p className="text-sm whitespace-pre-line text-fg">{inc.summary}</p>
            ) : (
              <p className="text-sm text-muted">No description yet. Add what you know as a note below.</p>
            )}
          </Card>

          {(manage || inc.tasks.length > 0) && (
            <Card padded={false}>
              <div className="p-5 pb-3">
                <CardHeader
                  title="Response tasks"
                  description="Containment, fixes and recovery steps, each with an owner and a deadline."
                  action={
                    manage &&
                    active && (
                      <Button size="sm" variant="secondary" onClick={() => setAddingTask(true)}>
                        <Plus className="size-4" /> Add task
                      </Button>
                    )
                  }
                />
              </div>
              {inc.tasks.length ? (
                <ul className="divide-y divide-border border-t border-border">
                  {inc.tasks.map((t) => (
                    <TaskRow key={t.id} task={t} showContext={false} />
                  ))}
                </ul>
              ) : (
                <p className="border-t border-border px-5 py-4 text-sm text-muted">
                  No tasks yet. Start with containment: isolate affected devices, reset compromised passwords, block the sender.
                </p>
              )}
            </Card>
          )}

          <Timeline inc={inc} onAdded={refresh} />
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Details" />
            <dl className="space-y-3 text-sm">
              <DetailRow label="Owner">
                {manage ? (
                  <AssigneeSelect
                    id="inc-owner"
                    value={inc.owner?.id ?? ""}
                    placeholder="No owner"
                    onChange={(v) => update.mutate(v ? { owner_id: v } : { clear_owner: true })}
                  />
                ) : (
                  inc.owner?.name ?? "Not assigned yet"
                )}
              </DetailRow>
              <DetailRow label="Severity">
                {manage ? (
                  <Select aria-label="Severity" value={inc.severity} onChange={(e) => update.mutate({ severity: e.target.value })}>
                    {SEVERITIES.filter((s) => s.value !== "informational").map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <SeverityBadge severity={inc.severity} />
                )}
              </DetailRow>
              <DetailRow label="Type">
                {manage ? (
                  <Select aria-label="Type" value={inc.category} onChange={(e) => update.mutate({ category: e.target.value })}>
                    {INCIDENT_CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </Select>
                ) : (
                  categoryName(inc.category)
                )}
              </DetailRow>
              {inc.contained_at && <DetailRow label="Contained">{formatDateTime(inc.contained_at)}</DetailRow>}
              {inc.resolved_at && <DetailRow label="Resolved">{formatDateTime(inc.resolved_at)}</DetailRow>}
            </dl>
          </Card>

          {(manage || inc.assets.length > 0) && (
            <Card>
              <CardHeader
                title="Affected assets"
                action={
                  manage &&
                  active && (
                    <Button size="sm" variant="ghost" onClick={() => setAddingAsset(true)} aria-label="Link an asset">
                      <Plus className="size-4" />
                    </Button>
                  )
                }
              />
              {inc.assets.length ? (
                <ul className="space-y-2">
                  {inc.assets.map((a) => (
                    <li key={a.id}>
                      <Link href={`/assets/${a.id}`} className="flex items-center gap-2 text-sm hover:text-primary-text">
                        <AssetIcon type={a.type} className="size-4 text-muted" />
                        <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
                        <span className="truncate text-xs text-subtle">{a.identifier}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">None linked.</p>
              )}
            </Card>
          )}

          {inc.alerts.length > 0 && (
            <Card>
              <CardHeader title="Related alerts" />
              <ul className="space-y-3">
                {inc.alerts.map((a) => (
                  <li key={a.id}>
                    <Link href={`/alerts/${a.id}`} className="block text-sm hover:text-primary-text">
                      <span className="font-medium">{a.title}</span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                        <SeverityBadge severity={a.severity} />
                        <AlertStatusBadge status={a.status} />
                        {a.asset_name} · {timeAgo(a.first_seen_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <EvidenceCard inc={inc} onAdded={refresh} />
        </div>
      </div>

      {closing && (
        <CloseDialog
          pending={update.isPending}
          error={update.isError ? errorMessage(update.error) : null}
          defaultSummary={inc.resolution_summary ?? ""}
          onClose={() => setClosing(false)}
          onSubmit={(reason, summary) =>
            update.mutate({ status: "closed", closure_reason: reason, resolution_summary: summary || undefined })
          }
        />
      )}
      {addingTask && <TaskDialog open incidentId={inc.id} onClose={() => setAddingTask(false)} />}
      {addingAsset && (
        <LinkAssetDialog
          incidentId={inc.id}
          linked={new Set(inc.assets.map((a) => a.id))}
          onClose={() => setAddingAsset(false)}
          onLinked={refresh}
        />
      )}
    </>
  );
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="text-fg">{children}</dd>
    </div>
  );
}

function Timeline({ inc, onAdded }: { inc: IncidentDetail; onAdded: () => void }) {
  const [note, setNote] = useState("");
  const add = useMutation({
    mutationFn: () => api(`/incidents/${inc.id}/notes`, { method: "POST", body: { body: note } }),
    onSuccess: () => {
      setNote("");
      onAdded();
    },
  });

  return (
    <Card>
      <CardHeader title="Timeline" description="Every action on this incident, recorded permanently for later review." />
      <form
        className="mb-5 space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (note.trim()) add.mutate();
        }}
      >
        <Textarea
          aria-label="Add a note"
          placeholder="Add an update — what you found, what you did, what's next…"
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={10000}
        />
        {add.isError && <p className="text-[13px] text-critical-text">{errorMessage(add.error)}</p>}
        <div className="flex justify-end">
          <Button size="sm" type="submit" loading={add.isPending} disabled={!note.trim()}>
            Add note
          </Button>
        </div>
      </form>
      <ol className="relative space-y-4 border-l border-border pl-5">
        {inc.timeline.map((ev) => (
          <li key={ev.id} className="relative">
            <span
              className={cn(
                "absolute top-0.5 -left-[29px] flex size-[17px] items-center justify-center rounded-full border border-border bg-surface text-muted",
                ev.event_type === "note" && "border-primary/40 text-primary-text",
              )}
            >
              {EVENT_ICON[ev.event_type] ?? <span className="size-1.5 rounded-full bg-current" />}
            </span>
            <p className="text-[13px] text-muted">
              <span className="font-medium text-fg">{ev.actor_label ?? "System"}</span>{" "}
              <span title={formatDateTime(ev.occurred_at)}>· {timeAgo(ev.occurred_at)}</span>
            </p>
            {ev.body && (
              <p className={cn("mt-0.5 text-sm whitespace-pre-line", ev.event_type === "note" ? "text-fg" : "text-muted")}>{ev.body}</p>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function EvidenceCard({ inc, onAdded }: { inc: IncidentDetail; onAdded: () => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api(`/incidents/${inc.id}/evidence`, { method: "POST", form });
    },
    onSuccess: () => {
      toast("success", "Evidence uploaded and encrypted.");
      onAdded();
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
  const download = (evId: string, name: string) =>
    downloadFile(`/incidents/${inc.id}/evidence/${evId}`, name).catch((e) => toast("error", errorMessage(e)));

  return (
    <Card>
      <CardHeader
        title="Evidence"
        description="Screenshots, logs or emails. Stored encrypted; downloads are logged."
        action={
          <Button size="sm" variant="ghost" loading={upload.isPending} onClick={() => input.current?.click()} aria-label="Upload evidence">
            <FileUp className="size-4" />
          </Button>
        }
      />
      <input
        ref={input}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          if (file.size > 10 * 1024 * 1024) toast("error", "Evidence files can be up to 10 MB.");
          else upload.mutate(file);
        }}
      />
      {inc.evidence.length ? (
        <ul className="space-y-2">
          {inc.evidence.map((ev) => (
            <li key={ev.id} className="flex items-center gap-2 text-sm">
              <Paperclip className="size-4 shrink-0 text-muted" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-fg">{ev.filename}</span>
                <span className="block text-xs text-subtle" title={`SHA-256 ${ev.sha256}`}>
                  {formatBytes(ev.size_bytes)} · {ev.uploaded_by_name ?? "Unknown"} · {timeAgo(ev.created_at)}
                </span>
              </span>
              <Button size="sm" variant="ghost" aria-label={`Download ${ev.filename}`} onClick={() => download(ev.id, ev.filename)}>
                <Download className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="w-full rounded-[var(--radius-control)] border border-dashed border-border px-3 py-5 text-center text-sm text-muted hover:border-primary/50 hover:text-fg"
        >
          Upload a file (up to 10 MB)
        </button>
      )}
    </Card>
  );
}

function CloseDialog({
  pending,
  error,
  defaultSummary,
  onClose,
  onSubmit,
}: {
  pending: boolean;
  error: string | null;
  defaultSummary: string;
  onClose: () => void;
  onSubmit: (reason: string, summary: string) => void;
}) {
  const [reason, setReason] = useState("resolved");
  const [summary, setSummary] = useState(defaultSummary);
  return (
    <Dialog
      open
      onClose={onClose}
      title="Close this incident?"
      description="Closing records the outcome for reports and audits. You can reopen it if something new comes up."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={pending} onClick={() => onSubmit(reason, summary)}>
            Close incident
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Callout tone="critical">{error}</Callout>}
        <Field label="Outcome" htmlFor="close-reason">
          <Select id="close-reason" value={reason} onChange={(e) => setReason(e.target.value)}>
            {CLOSURE_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Lessons learned" htmlFor="close-summary" optional hint="Root cause, what was done, and what would prevent it next time.">
          <Textarea id="close-summary" rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Field>
      </div>
    </Dialog>
  );
}

function LinkAssetDialog({
  incidentId,
  linked,
  onClose,
  onLinked,
}: {
  incidentId: string;
  linked: Set<string>;
  onClose: () => void;
  onLinked: () => void;
}) {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: useOrgKey("assets", "picker", q),
    queryFn: () => api<Page<Asset>>("/assets", { query: { q, page_size: 20 } }),
  });
  const link = useMutation({
    mutationFn: (assetId: string) =>
      api(`/incidents/${incidentId}/assets`, { method: "POST", body: { asset_id: assetId } }),
    onSuccess: () => {
      onLinked();
      onClose();
    },
  });
  const options = (data?.items ?? []).filter((a) => !linked.has(a.id));
  return (
    <Dialog open onClose={onClose} title="Link an affected asset">
      <div className="space-y-3">
        {link.isError && <Callout tone="critical">{errorMessage(link.error)}</Callout>}
        <Input aria-label="Search assets" placeholder="Search assets" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
        <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-[var(--radius-control)] border border-border">
          {options.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                disabled={link.isPending}
                onClick={() => link.mutate(a.id)}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-surface-2"
              >
                <AssetIcon type={a.type} className="size-4 text-muted" />
                <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
                <span className="truncate text-xs text-subtle">{a.identifier}</span>
              </button>
            </li>
          ))}
          {!options.length && <li className="px-3 py-4 text-center text-sm text-muted">No matching assets.</li>}
        </ul>
      </div>
    </Dialog>
  );
}
