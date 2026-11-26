"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useOrgLookups } from "@/components/asset-form";
import { CopyField } from "@/components/copy-field";
import { Dialog } from "@/components/dialog";
import { useOrgKey } from "@/components/session";
import { Button, Callout, Field, Input, Select, cn } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AgentRelease, EnrolmentToken } from "@/lib/types";

type Created = { token: string; details: EnrolmentToken };

const OS_TABS = [
  { id: "windows", label: "Windows" },
  { id: "macos", label: "macOS" },
  { id: "linux", label: "Linux" },
  { id: "wazuh", label: "Wazuh" },
] as const;

function CodeBlock({ lines }: { lines: string[] }) {
  const text = lines.join("\n");
  return (
    <div className="overflow-hidden rounded-[var(--radius-control)] bg-navy dark:bg-black/40">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5">
        <span className="text-[11px] tracking-wide text-slate-400 uppercase">Commands</span>
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(text)}
          className="rounded-md bg-white/10 px-2 py-0.5 text-xs text-slate-200 hover:bg-white/20"
        >
          Copy
        </button>
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-[12.5px] leading-relaxed text-slate-100">{text}</pre>
    </div>
  );
}

function Instructions({ token }: { token: string }) {
  const [tab, setTab] = useState<(typeof OS_TABS)[number]["id"]>("windows");
  const { data: release } = useQuery({
    queryKey: ["agent-release"],
    queryFn: () => api<AgentRelease>("/agent/release", { org: false }),
    staleTime: Infinity,
  });
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const download = `${origin}/api/v1/agent/download`;
  // Agents refuse plain HTTP. Only a local development server runs without HTTPS.
  const insecure = origin.startsWith("http://") ? " --allow-insecure-http" : "";

  return (
    <div className="space-y-4">
      <CopyField label="Enrolment token" value={token} />
      <Callout tone="warning">
        Copy this token now. It won&apos;t be shown again. Anyone with it can add devices to
        your organisation until it expires or is used up.
      </Callout>
      <div role="tablist" className="flex gap-1 border-b border-border">
        {OS_TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm",
              tab === t.id ? "border-primary font-medium text-primary-text" : "border-transparent text-muted hover:text-fg",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "windows" && (
        <div className="space-y-2 text-sm text-muted">
          <p>In PowerShell as Administrator (Python 3.10+ required):</p>
          <CodeBlock
            lines={[
              `Invoke-WebRequest ${download} -OutFile smecm_agent.py`,
              "Get-FileHash smecm_agent.py -Algorithm SHA256",
              `py smecm_agent.py enrol --server ${origin} --token ${token}${insecure}`,
              "py smecm_agent.py run",
            ]}
          />
        </div>
      )}
      {(tab === "macos" || tab === "linux") && (
        <div className="space-y-2 text-sm text-muted">
          <p>
            In Terminal{tab === "linux" ? " (use sudo so the agent can read sign-in logs)" : ""}:
          </p>
          <CodeBlock
            lines={[
              `curl -fsSLo smecm_agent.py ${download}`,
              tab === "macos" ? "shasum -a 256 smecm_agent.py" : "sha256sum smecm_agent.py",
              `${tab === "linux" ? "sudo " : ""}python3 smecm_agent.py enrol --server ${origin} --token ${token}${insecure}`,
              `${tab === "linux" ? "sudo " : ""}python3 smecm_agent.py run`,
            ]}
          />
        </div>
      )}
      {tab === "wazuh" ? (
        <p className="text-sm text-muted">
          Already use Wazuh, or need full endpoint detection (malware, processes, Windows
          events)? Connect your Wazuh manager once in{" "}
          <Link href="/settings/integrations" className="text-primary-text underline">
            Settings → Integrations
          </Link>
          . Devices with a Wazuh agent then appear here automatically. No token needed.
        </p>
      ) : (
        <>
          {release && (
            <p className="text-xs text-subtle">
              The checksum should be <code className="font-mono break-all text-fg">{release.sha256}</code>{" "}
              (agent v{release.version}). Don&apos;t run the agent if it differs.
            </p>
          )}
          {insecure && (
            <p className="text-xs text-warning-text">
              This server isn&apos;t using HTTPS, so the commands include --allow-insecure-http.
              That&apos;s only acceptable for local testing.
            </p>
          )}
          <p className="text-xs text-subtle">
            Keep <code>run</code> going as a service so the device keeps reporting. Signed installers for
            Windows, macOS and Linux are planned before commercial launch.
          </p>
        </>
      )}
    </div>
  );
}

export function EnrolDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const { departments } = useOrgLookups();
  const [form, setForm] = useState({ label: "", asset_type: "workstation", department_id: "", valid_hours: 24, max_uses: 1 });
  const [created, setCreated] = useState<Created | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api<Created>("/endpoints/enrolment-tokens", {
        method: "POST",
        body: { ...form, label: form.label || null, department_id: form.department_id || null },
      }),
    onSuccess: (res) => {
      setCreated(res);
      queryClient.invalidateQueries({ queryKey: [...orgKey, "enrolment-tokens"] });
    },
  });

  function close() {
    setCreated(null);
    create.reset();
    onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      wide
      title={created ? "Install the agent" : "Add devices"}
      description={
        created
          ? `Token valid until ${formatDateTime(created.details.expires_at)} for ${created.details.max_uses} device(s).`
          : "Create a short-lived enrolment token, then install the monitoring agent with it."
      }
      footer={
        created ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" form="enrol-form" loading={create.isPending}>
              Create token
            </Button>
          </>
        )
      }
    >
      {created ? (
        <Instructions token={created.token} />
      ) : (
        <form
          id="enrol-form"
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          {create.isError && (
            <div className="sm:col-span-2">
              <Callout tone="critical">{errorMessage(create.error)}</Callout>
            </div>
          )}
          <Field label="Device type" htmlFor="enrol-type">
            <Select id="enrol-type" value={form.asset_type} onChange={(e) => setForm((f) => ({ ...f, asset_type: e.target.value }))}>
              <option value="workstation">Workstation</option>
              <option value="laptop">Laptop</option>
              <option value="server">Server</option>
            </Select>
          </Field>
          <Field label="Department" htmlFor="enrol-dept" optional>
            <Select id="enrol-dept" value={form.department_id} onChange={(e) => setForm((f) => ({ ...f, department_id: e.target.value }))}>
              <option value="">No department</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Number of devices" htmlFor="enrol-uses" hint="Each device uses the token once.">
            <Input
              id="enrol-uses"
              type="number"
              min={1}
              max={500}
              value={form.max_uses}
              onChange={(e) => setForm((f) => ({ ...f, max_uses: Number(e.target.value) || 1 }))}
            />
          </Field>
          <Field label="Valid for" htmlFor="enrol-valid">
            <Select id="enrol-valid" value={form.valid_hours} onChange={(e) => setForm((f) => ({ ...f, valid_hours: Number(e.target.value) }))}>
              <option value={1}>1 hour</option>
              <option value={24}>24 hours</option>
              <option value={72}>3 days</option>
              <option value={168}>7 days</option>
            </Select>
          </Field>
          <Field label="Label" htmlFor="enrol-label" optional className="sm:col-span-2">
            <Input id="enrol-label" value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} placeholder="e.g. Accounts team laptops" />
          </Field>
          <p className="flex gap-2 text-[13px] text-muted sm:col-span-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
            Installing the agent proves your organisation controls the device, so enrolled devices
            are authorised for monitoring automatically.
          </p>
        </form>
      )}
    </Dialog>
  );
}
