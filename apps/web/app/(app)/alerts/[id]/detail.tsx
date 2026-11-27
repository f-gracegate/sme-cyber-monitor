"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, Eye, Search, Siren } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { FindingExplainer } from "@/components/finding-explainer";
import { IncidentStatusBadge } from "@/components/incident-ui";
import { AlertStatusBadge, SeverityBadge } from "@/components/monitoring-ui";
import { useToast } from "@/components/providers";
import { ReportIncidentDialog } from "@/components/report-incident-dialog";
import { useOrgKey, useSession } from "@/components/session";
import {
  Button,
  ButtonLink,
  Callout,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Skeleton,
  Textarea,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AlertDetail } from "@/lib/types";

export function Detail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState<"fixed" | "false_positive" | "expected">("fixed");
  const [mute, setMute] = useState(false);
  const [muteDays, setMuteDays] = useState("90");
  const [escalating, setEscalating] = useState(false);

  const key = [...orgKey, "alert", id];
  const { data: alert, isPending, error } = useQuery({
    queryKey: key,
    queryFn: () => api<AlertDetail>(`/alerts/${id}`),
  });
  const update = useMutation({
    mutationFn: async (body: { status: string; note?: string; outcome?: string; mute?: boolean }) => {
      const { mute: muteToo, ...patch } = body;
      const updated = await api<AlertDetail>(`/alerts/${id}`, { method: "PATCH", body: patch });
      if (muteToo) {
        await api("/suppression-rules", {
          method: "POST",
          body: {
            alert_id: id,
            reason: note.trim() || (outcome === "false_positive" ? "Not a real problem" : "Known and expected"),
            expires_in_days: muteDays === "never" ? undefined : Number(muteDays),
          },
        });
      }
      return updated;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      queryClient.invalidateQueries({ queryKey: orgKey });
      setResolving(false);
      toast("success", `Alert ${data.status === "resolved" ? "resolved" : "updated"}.`);
    },
  });

  const back = (
    <Link href="/alerts" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
      <ArrowLeft className="size-4" /> Alerts
    </Link>
  );
  if (isPending) return <Skeleton className="h-96" />;
  if (error || !alert) {
    return (
      <>
        {back}
        <Card>
          <EmptyState title="Alert not found" description={errorMessage(error)} />
        </Card>
      </>
    );
  }

  const manage = can("alerts:manage") && alert.status !== "resolved";
  return (
    <>
      <PageHeader
        back={back}
        title={alert.title}
        actions={
          <>
            {!alert.incident && can("incidents:manage") && (
              <Button variant="secondary" onClick={() => setEscalating(true)}>
                <Siren className="size-4" /> Open incident
              </Button>
            )}
            <ButtonLink href={`/findings/${alert.finding_id}`} variant="secondary">
              <Search className="size-4" /> Finding
            </ButtonLink>
            {manage && alert.status === "new" && (
              <Button variant="secondary" loading={update.isPending} onClick={() => update.mutate({ status: "acknowledged" })}>
                <Eye className="size-4" /> Acknowledge
              </Button>
            )}
            {manage && alert.status !== "investigating" && (
              <Button variant="secondary" loading={update.isPending} onClick={() => update.mutate({ status: "investigating" })}>
                Start investigating
              </Button>
            )}
            {manage && (
              <Button onClick={() => setResolving(true)}>
                <CircleCheck className="size-4" /> Resolve
              </Button>
            )}
          </>
        }
      />
      <div className="mb-5 flex flex-wrap items-center gap-2 text-sm text-muted">
        <SeverityBadge severity={alert.severity} />
        <AlertStatusBadge status={alert.status} />
        <span>Raised {formatDateTime(alert.first_seen_at)}</span>
        {alert.occurrences > 1 && <span>· seen {alert.occurrences} times</span>}
        {alert.acknowledged_by_name && <span>· acknowledged by {alert.acknowledged_by_name}</span>}
      </div>
      {alert.incident && (
        <div className="mb-5">
          <Callout
            tone="primary"
            icon={<Siren className="size-4" />}
            title={
              <span className="inline-flex flex-wrap items-center gap-2">
                Part of {alert.incident.reference}: {alert.incident.title}
                <IncidentStatusBadge status={alert.incident.status} />
              </span>
            }
            action={
              <ButtonLink href={`/incidents/${alert.incident.id}`} size="sm" variant="secondary">
                Open incident
              </ButtonLink>
            }
          >
            The response to this alert is being coordinated in the incident.
          </Callout>
        </div>
      )}
      {alert.status === "resolved" && (
        <div className="mb-5">
          <Callout tone="success" title={alert.resolved_by_name ? `Resolved by ${alert.resolved_by_name}` : "Resolved automatically"}>
            {formatDateTime(alert.resolved_at)}
            {alert.resolution_note && <span className="block italic">&ldquo;{alert.resolution_note}&rdquo;</span>}
          </Callout>
        </div>
      )}
      <FindingExplainer finding={alert.finding} />
      {escalating && (
        <ReportIncidentDialog
          open
          onClose={() => setEscalating(false)}
          alertIds={[alert.id]}
          assetIds={[alert.asset_id]}
          defaultTitle={alert.asset ? `${alert.title} on ${alert.asset.name}` : alert.title}
        />
      )}

      <Dialog
        open={resolving}
        onClose={() => setResolving(false)}
        title="Resolve this alert?"
        description="Resolving closes the alert. The underlying finding stays open until monitoring confirms it's fixed (or you mark it fixed), and a new alert opens if it comes back."
        footer={
          <>
            <Button variant="secondary" onClick={() => setResolving(false)}>
              Cancel
            </Button>
            <Button
              loading={update.isPending}
              onClick={() => update.mutate({ status: "resolved", note: note || undefined, outcome, mute: mute && outcome !== "fixed" })}
            >
              Resolve alert
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {update.isError && <Callout tone="critical">{errorMessage(update.error)}</Callout>}
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-fg">What was it?</legend>
            <div className="grid gap-2">
              {(
                [
                  ["fixed", "A real problem, now fixed", "We dealt with it."],
                  ["false_positive", "Not a real problem", "The alert was wrong. This helps us tune detection."],
                  ["expected", "Known and expected", "It's real but fine for us (for example, handled elsewhere)."],
                ] as const
              ).map(([value, label, hint]) => (
                <label
                  key={value}
                  className={`flex cursor-pointer gap-3 rounded-[var(--radius-control)] border p-3 text-sm ${outcome === value ? "border-primary ring-1 ring-primary" : "border-border hover:bg-surface-2"}`}
                >
                  <input type="radio" name="outcome" value={value} checked={outcome === value} onChange={() => setOutcome(value)} className="mt-0.5 accent-[var(--color-primary)]" />
                  <span>
                    <span className="block font-medium text-fg">{label}</span>
                    <span className="block text-[13px] text-muted">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {outcome !== "fixed" && alert.severity !== "critical" && (
            <div className="rounded-[var(--radius-control)] border border-border p-3 text-sm">
              <label className="flex items-center gap-2 font-medium text-fg">
                <input type="checkbox" checked={mute} onChange={(e) => setMute(e.target.checked)} />
                Don&apos;t alert about this again{alert.asset ? ` on ${alert.asset.name}` : ""}
              </label>
              {mute && (
                <div className="mt-2 flex items-center gap-2 text-muted">
                  <span>For</span>
                  <select
                    aria-label="Mute for"
                    value={muteDays}
                    onChange={(e) => setMuteDays(e.target.value)}
                    className="rounded-md border border-border bg-surface px-2 py-1 text-sm text-fg"
                  >
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="365">a year</option>
                    <option value="never">until I unmute it</option>
                  </select>
                  <span>· findings are still recorded</span>
                </div>
              )}
            </div>
          )}
          <Field label={outcome === "fixed" ? "What was done?" : "Why?"} htmlFor="alert-note" optional>
            <Textarea id="alert-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </Field>
        </div>
      </Dialog>
    </>
  );
}
