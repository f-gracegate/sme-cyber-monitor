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
  const [escalating, setEscalating] = useState(false);

  const key = [...orgKey, "alert", id];
  const { data: alert, isPending, error } = useQuery({
    queryKey: key,
    queryFn: () => api<AlertDetail>(`/alerts/${id}`),
  });
  const update = useMutation({
    mutationFn: (body: { status: string; note?: string }) =>
      api<AlertDetail>(`/alerts/${id}`, { method: "PATCH", body }),
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
            <Button loading={update.isPending} onClick={() => update.mutate({ status: "resolved", note: note || undefined })}>
              Resolve alert
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {update.isError && <Callout tone="critical">{errorMessage(update.error)}</Callout>}
          <Field label="What was done?" htmlFor="alert-note" optional>
            <Textarea id="alert-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </Field>
        </div>
      </Dialog>
    </>
  );
}
