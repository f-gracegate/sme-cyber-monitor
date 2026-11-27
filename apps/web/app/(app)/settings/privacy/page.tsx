"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileArchive } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Callout, Card, CardHeader, Field, Input, Select, Skeleton } from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import type { DataExport, Organisation, Retention } from "@/lib/types";

const RETENTION_CHOICES = [7, 14, 30, 60, 90, 180, 365];

function RetentionCard() {
  const { orgId, can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("retention");
  const { data } = useQuery({ queryKey: key, queryFn: () => api<Retention>(`/organisations/${orgId}/retention`, { org: false }) });
  const save = useMutation({
    mutationFn: (days: number) =>
      api<Retention>(`/organisations/${orgId}/retention`, { method: "PUT", body: { telemetry_retention_days: days }, org: false }),
    onSuccess: (r) => {
      queryClient.setQueryData(key, r);
      toast("success", `Raw monitoring data is now kept for ${r.telemetry_retention_days} days.`);
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader
        title="How long we keep monitoring data"
        description="Security events from devices and the results of individual checks are deleted after this period. Findings, alerts, incidents, reports and the audit history are kept while you're a customer."
      />
      {!data ? (
        <Skeleton className="h-10" />
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Keep raw data for" htmlFor="retention">
            <Select
              id="retention"
              value={data.telemetry_retention_days}
              disabled={!can("org:update") || save.isPending}
              onChange={(e) => save.mutate(Number(e.target.value))}
            >
              {RETENTION_CHOICES.filter((d) => !data.max_days || d <= data.max_days || d === data.telemetry_retention_days).map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </Select>
          </Field>
          {data.max_days && <p className="pb-2 text-[13px] text-muted">Your plan allows up to {data.max_days} days.</p>}
        </div>
      )}
    </Card>
  );
}

function ExportCard() {
  const { orgId } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("exports");
  const { data } = useQuery({ queryKey: key, queryFn: () => api<DataExport[]>(`/organisations/${orgId}/exports`, { org: false }) });
  const create = useMutation({
    mutationFn: () => api<DataExport>(`/organisations/${orgId}/exports`, { method: "POST", org: false }),
    onSuccess: (e) => {
      queryClient.invalidateQueries({ queryKey: key });
      toast("success", "Export ready.");
      void download(e);
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
  const download = (e: DataExport) =>
    downloadFile(`/organisations/${orgId}/exports/${e.id}/download`, "data-export.zip").catch((err) => toast("error", errorMessage(err)));
  return (
    <Card>
      <CardHeader
        title="Export your data"
        description="A zip of every record we hold for this organisation, as JSON: assets, findings, alerts, incidents, tasks, members, monitoring data and the audit history. Passwords and keys are never included. Each export can be downloaded for 7 days."
        action={
          <Button loading={create.isPending} onClick={() => create.mutate()}>
            <FileArchive className="size-4" /> Create export
          </Button>
        }
      />
      {data && data.length > 0 && (
        <ul className="divide-y divide-border">
          {data.map((e) => (
            <li key={e.id} className="flex items-center gap-3 py-2.5 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block text-fg">
                  {formatDateTime(e.created_at)} · {e.requested_by_name ?? "—"}
                </span>
                <span className="block truncate text-[13px] text-muted">
                  {e.status === "ready" ? `${((e.size_bytes ?? 0) / 1024).toFixed(0)} KB · available until ${formatDate(e.expires_at)}` : "Expired"}
                </span>
              </span>
              {e.status === "ready" && (
                <Button size="sm" variant="secondary" aria-label="Download export" onClick={() => download(e)}>
                  <Download className="size-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function DeleteOrganisationCard() {
  const { orgId, membership } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey("organisation");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const { data: org } = useQuery({ queryKey: orgKey, queryFn: () => api<Organisation>(`/organisations/${orgId}`, { org: false }) });
  const request = useMutation({
    mutationFn: () =>
      api(`/organisations/${orgId}/deletion`, { method: "POST", body: { confirm_name: name, password }, org: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      setOpen(false);
      toast("success", "Deletion scheduled. Owners have been emailed.");
    },
  });
  const cancel = useMutation({
    mutationFn: () => api(`/organisations/${orgId}/deletion`, { method: "DELETE", org: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", "Deletion cancelled.");
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
  if (!org) return null;
  return (
    <Card>
      <CardHeader
        title="Delete this organisation"
        description="Monitoring stops for good and, after 30 days, every asset, alert, incident, evidence file, report and monitoring record is erased. Billing records and the audit history are kept, as the law requires. Export your data first if you need a copy."
      />
      {org.deletion_scheduled_for ? (
        <Callout
          tone="critical"
          title={`Scheduled for deletion on ${formatDate(org.deletion_scheduled_for)}`}
          action={
            <Button size="sm" variant="secondary" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel deletion
            </Button>
          }
        >
          Everything will be erased on that date.
        </Callout>
      ) : (
        <Button variant="danger" onClick={() => setOpen(true)}>
          Delete organisation
        </Button>
      )}
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={`Delete ${membership?.organisation_name}?`}
        description="You have 30 days to change your mind. After that, deletion can't be undone."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Keep it
            </Button>
            <Button variant="danger" loading={request.isPending} disabled={name !== org.name || !password} onClick={() => request.mutate()}>
              Schedule deletion
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {request.isError && <Callout tone="critical">{errorMessage(request.error)}</Callout>}
          <Field label={`Type "${org.name}" to confirm`} htmlFor="del-name">
            <Input id="del-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" />
          </Field>
          <Field label="Your password" htmlFor="del-pass">
            <Input id="del-pass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
        </div>
      </Dialog>
    </Card>
  );
}

function DeleteAccountCard() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const remove = useMutation({
    mutationFn: () => api("/me/delete-account", { method: "POST", body: { password }, org: false }),
    onSuccess: () => router.replace("/login"),
  });
  return (
    <Card>
      <CardHeader
        title="Delete my account"
        description="Removes you from every organisation and erases your name, email and sign-in details. Actions you took stay in audit histories as “Deleted user”."
      />
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Delete my account
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Delete your account?"
        description="This can't be undone. If you're the only owner of an organisation, make someone else an owner first."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} disabled={!password} onClick={() => remove.mutate()}>
              Delete account
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {remove.isError && <Callout tone="critical">{errorMessage(remove.error)}</Callout>}
          <Field label="Your password" htmlFor="acct-pass">
            <Input id="acct-pass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
        </div>
      </Dialog>
    </Card>
  );
}

export default function PrivacySettingsPage() {
  const { membership, can } = useSession();
  const manager = membership && (membership.role === "owner" || membership.role === "admin");
  return (
    <div className="space-y-6">
      {membership && <RetentionCard />}
      {manager && can("org:update") && <ExportCard />}
      {membership?.role === "owner" && <DeleteOrganisationCard />}
      <DeleteAccountCard />
      <p className="text-[13px] text-muted">
        We process your organisation&apos;s data on your behalf under the Data Protection Act, 2012 (Act 843). See the{" "}
        <a href="/legal/privacy" className="underline">
          privacy notice
        </a>{" "}
        for your rights and how to contact us.
      </p>
    </div>
  );
}
