"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bell, CircleCheck, RotateCcw, ShieldOff, Wrench } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { FindingExplainer } from "@/components/finding-explainer";
import { TaskDialog, TaskRow } from "@/components/incident-ui";
import { FindingStatusBadge, SeverityBadge } from "@/components/monitoring-ui";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import {
  Button,
  ButtonLink,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Field,
  PageHeader,
  Skeleton,
  Textarea,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { FindingDetail, Page, Task } from "@/lib/types";

type Action = { status: "resolved" | "accepted_risk"; title: string; description: string };

export function Detail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [action, setAction] = useState<Action | null>(null);
  const [note, setNote] = useState("");
  const [assigning, setAssigning] = useState(false);

  const key = [...orgKey, "finding", id];
  const { data: finding, isPending, error } = useQuery({
    queryKey: key,
    queryFn: () => api<FindingDetail>(`/findings/${id}`),
  });
  const tasks = useQuery({
    queryKey: [...orgKey, "remediation-tasks", "finding", id],
    queryFn: () =>
      api<Page<Task>>("/remediation-tasks", {
        query: { finding_id: id, status: ["open", "in_progress", "done", "verified", "cancelled"] },
      }),
    enabled: can("org:read"),
  });
  const update = useMutation({
    mutationFn: (body: { status: string; note?: string }) =>
      api<FindingDetail>(`/findings/${id}`, { method: "PATCH", body }),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      queryClient.invalidateQueries({ queryKey: orgKey });
      setAction(null);
      setNote("");
      toast("success", "Finding updated.");
    },
  });

  const back = (
    <Link href="/findings" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
      <ArrowLeft className="size-4" /> Findings
    </Link>
  );
  if (isPending) return <Skeleton className="h-96" />;
  if (error || !finding) {
    return (
      <>
        {back}
        <Card>
          <EmptyState title="Finding not found" description={errorMessage(error)} />
        </Card>
      </>
    );
  }

  const manage = can("findings:manage");
  const activeTask = tasks.data?.items.some((t) => ["open", "in_progress", "done"].includes(t.status));
  return (
    <>
      <PageHeader
        back={back}
        title={finding.title}
        actions={
          <>
            {finding.open_alert_id && (
              <ButtonLink href={`/alerts/${finding.open_alert_id}`} variant="secondary">
                <Bell className="size-4" /> View alert
              </ButtonLink>
            )}
            {can("remediation:manage") && finding.status === "open" && !activeTask && (
              <Button variant="secondary" onClick={() => setAssigning(true)}>
                <Wrench className="size-4" /> Assign fix
              </Button>
            )}
            {manage && finding.status === "open" && (
              <>
                <Button
                  variant="secondary"
                  onClick={() =>
                    setAction({
                      status: "accepted_risk",
                      title: "Accept this risk?",
                      description:
                        "Monitoring keeps tracking it, but it won't raise alerts or count against your score's open items. Record why for your auditors.",
                    })
                  }
                >
                  <ShieldOff className="size-4" /> Accept risk
                </Button>
                <Button
                  onClick={() =>
                    setAction({
                      status: "resolved",
                      title: "Mark as fixed?",
                      description:
                        "If monitoring still detects the problem on its next run, the finding reopens and a new alert is raised.",
                    })
                  }
                >
                  <CircleCheck className="size-4" /> Mark fixed
                </Button>
              </>
            )}
            {manage && finding.status !== "open" && (
              <Button variant="secondary" loading={update.isPending} onClick={() => update.mutate({ status: "open" })}>
                <RotateCcw className="size-4" /> Reopen
              </Button>
            )}
          </>
        }
      />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <FindingStatusBadge status={finding.status} />
      </div>
      {finding.sticky && finding.status === "open" && (
        <div className="mb-5">
          <Callout tone="warning">
            This is a one-off change, so it stays open until someone confirms it was expected.
          </Callout>
        </div>
      )}
      {finding.status === "resolved" && !finding.resolved_by_name && (
        <div className="mb-5">
          <Callout tone="success">Monitoring confirmed this is fixed.</Callout>
        </div>
      )}
      <FindingExplainer finding={finding} />
      {!!tasks.data?.items.length && (
        <Card padded={false} className="mt-5">
          <div className="p-5 pb-3">
            <CardHeader title="Remediation" description="Who is fixing this, and by when." />
          </div>
          <ul className="divide-y divide-border border-t border-border">
            {tasks.data.items.map((t) => (
              <TaskRow key={t.id} task={t} showContext={false} />
            ))}
          </ul>
        </Card>
      )}
      {assigning && (
        <TaskDialog open findingId={finding.id} onClose={() => setAssigning(false)} />
      )}

      <Dialog
        open={action !== null}
        onClose={() => setAction(null)}
        title={action?.title ?? ""}
        description={action?.description}
        footer={
          <>
            <Button variant="secondary" onClick={() => setAction(null)}>
              Cancel
            </Button>
            <Button
              loading={update.isPending}
              disabled={action?.status === "accepted_risk" && !note.trim()}
              onClick={() => action && update.mutate({ status: action.status, note: note || undefined })}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {update.isError && <Callout tone="critical">{errorMessage(update.error)}</Callout>}
          <Field
            label={action?.status === "accepted_risk" ? "Reason (required)" : "Note"}
            htmlFor="finding-note"
            optional={action?.status !== "accepted_risk"}
          >
            <Textarea id="finding-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </Field>
        </div>
      </Dialog>
    </>
  );
}
