"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { AssigneeSelect } from "@/components/incident-ui";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Callout, Field, Input, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { INCIDENT_CATEGORIES, SEVERITIES } from "@/lib/labels";
import type { Incident } from "@/lib/types";

/** Staff report a suspected incident; responders can also open one directly with severity/owner. */
export function ReportIncidentDialog({
  open,
  onClose,
  alertIds,
  assetIds,
  defaultTitle = "",
}: {
  open: boolean;
  onClose: () => void;
  alertIds?: string[];
  assetIds?: string[];
  defaultTitle?: string;
}) {
  const { can } = useSession();
  const responder = can("incidents:manage");
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [title, setTitle] = useState(defaultTitle);
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState("other");
  const [severity, setSeverity] = useState("");
  const [owner, setOwner] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api<Incident>("/incidents", {
        method: "POST",
        body: {
          title,
          summary,
          category,
          severity: severity || undefined,
          owner_id: owner || undefined,
          alert_ids: alertIds ?? [],
          asset_ids: assetIds ?? [],
        },
      }),
    onSuccess: (inc) => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", responder ? `${inc.reference} opened.` : `Thanks — ${inc.reference} was sent to your security team.`);
      onClose();
      router.push(`/incidents/${inc.id}`);
    },
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={responder ? "Open an incident" : "Report a security incident"}
      description={
        responder
          ? "Use an incident to coordinate the response to something that has (or may have) gone wrong."
          : "Tell us what you noticed. Don't worry if you're not sure it's serious — reporting early is always the right call. Don't forward suspicious emails to colleagues; attach a screenshot instead."
      }
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} disabled={!title.trim()} onClick={() => create.mutate()}>
            {responder ? "Open incident" : "Send report"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {create.isError && <Callout tone="critical">{errorMessage(create.error)}</Callout>}
        <Field label="What happened?" htmlFor="inc-title" hint="A short headline, e.g. “Clicked a link in a fake invoice email”.">
          <Input id="inc-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus />
        </Field>
        <Field label="Type" htmlFor="inc-category">
          <Select id="inc-category" value={category} onChange={(e) => setCategory(e.target.value)}>
            {INCIDENT_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Details"
          htmlFor="inc-summary"
          optional
          hint="When did it happen, which device or account, and what have you done since?"
        >
          <Textarea id="inc-summary" rows={5} value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={10000} />
        </Field>
        {responder && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Severity" htmlFor="inc-severity" optional hint="Defaults from linked alerts, otherwise medium.">
              <Select id="inc-severity" value={severity} onChange={(e) => setSeverity(e.target.value)}>
                <option value="">Automatic</option>
                {SEVERITIES.filter((s) => s.value !== "informational").map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Owner" htmlFor="inc-owner" optional>
              <AssigneeSelect id="inc-owner" value={owner} onChange={setOwner} placeholder="No owner yet" />
            </Field>
          </div>
        )}
      </div>
    </Dialog>
  );
}
