"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bell, CircleCheck, RotateCcw, ShieldOff } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { FindingExplainer } from "@/components/finding-explainer";
import { FindingStatusBadge, SeverityBadge } from "@/components/monitoring-ui";
import { useToast } from "@/components/providers";
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
import type { FindingDetail } from "@/lib/types";

type Action = { status: "resolved" | "accepted_risk"; title: string; description: string };

export function Detail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [action, setAction] = useState<Action | null>(null);
  const [note, setNote] = useState("");

  const key = [...orgKey, "finding", id];
  const { data: finding, isPending, error } = useQuery({
    queryKey: key,
    queryFn: () => api<FindingDetail>(`/findings/${id}`),
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
