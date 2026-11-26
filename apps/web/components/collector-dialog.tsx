"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CopyField } from "@/components/copy-field";
import { Dialog } from "@/components/dialog";
import { useOrgKey } from "@/components/session";
import { Button, Callout, Field, Input, cn } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AgentRelease, EnrolmentToken } from "@/lib/types";

function Commands({ lines }: { lines: string[] }) {
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
  const [tab, setTab] = useState<"docker" | "python" | "devices">("docker");
  const { data: release } = useQuery({
    queryKey: ["collector-release"],
    queryFn: () => api<AgentRelease>("/collector/release", { org: false }),
    staleTime: Infinity,
  });
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const insecure = origin.startsWith("http://") ? " --allow-insecure-http" : "";

  return (
    <div className="space-y-4">
      <CopyField label="Collector enrolment token" value={token} />
      <Callout tone="warning">Copy this token now. It won&apos;t be shown again.</Callout>
      <div role="tablist" className="flex gap-1 border-b border-border">
        {(
          [
            ["docker", "Docker (recommended)"],
            ["python", "Python"],
            ["devices", "Point your devices"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm",
              tab === id ? "border-primary font-medium text-primary-text" : "border-transparent text-muted hover:text-fg",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "docker" && (
        <div className="space-y-2 text-sm text-muted">
          <p>On a small always-on Linux machine or VM inside your office network:</p>
          <Commands
            lines={[
              `curl -fsSLo smecm_collector.py ${origin}/api/v1/collector/download`,
              "sha256sum smecm_collector.py",
              "docker volume create smecm-collector",
              `docker run --rm -v smecm-collector:/state -v "$PWD":/opt/smecm python:3.13-slim \\`,
              `  python /opt/smecm/smecm_collector.py --config /state/collector.json \\`,
              `  enrol --server ${origin} --token ${token}${insecure}`,
              `docker run -d --name smecm-collector --restart unless-stopped \\`,
              `  -p 5514:5514/udp -p 5514:5514/tcp -v smecm-collector:/state -v "$PWD":/opt/smecm \\`,
              `  python:3.13-slim python /opt/smecm/smecm_collector.py --config /state/collector.json run`,
            ]}
          />
        </div>
      )}
      {tab === "python" && (
        <div className="space-y-2 text-sm text-muted">
          <p>
            Python 3.10+ on Linux. Add <code>--suricata-eve</code> or <code>--zeek-dir</code> if a
            network sensor runs on the same machine.
          </p>
          <Commands
            lines={[
              `curl -fsSLo smecm_collector.py ${origin}/api/v1/collector/download`,
              "sha256sum smecm_collector.py",
              `python3 smecm_collector.py enrol --server ${origin} --token ${token}${insecure} \\`,
              "  [--suricata-eve /var/log/suricata/eve.json] [--zeek-dir /opt/zeek/logs/current]",
              "python3 smecm_collector.py run",
            ]}
          />
        </div>
      )}
      {tab === "devices" && (
        <div className="space-y-2 text-sm text-muted">
          <p>
            Send syslog from your firewalls, routers and switches to the collector&apos;s IP
            address on port <strong>5514</strong> (UDP or TCP). Supported formats: FortiGate,
            Cisco ASA, pfSense/OPNsense, MikroTik, and Linux iptables/UFW.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Only blocked connections, configuration changes and admin logins are forwarded. Allowed-traffic logs are dropped.</li>
            <li>The collector only accepts logs from private network addresses unless you change its settings.</li>
            <li>Register each firewall and router as an asset using its management IP, and confirm authorisation, so the collector checks it&apos;s reachable.</li>
          </ul>
        </div>
      )}
      {release && (
        <p className="text-xs text-subtle">
          Checksum should be <code className="font-mono break-all text-fg">{release.sha256}</code> (collector v{release.version}).
        </p>
      )}
      {insecure && (
        <p className="text-xs text-warning-text">
          This server isn&apos;t using HTTPS, so the commands include --allow-insecure-http. Only for
          local testing.
        </p>
      )}
    </div>
  );
}

export function CollectorDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [label, setLabel] = useState("Head office");
  const [created, setCreated] = useState<{ token: string; details: EnrolmentToken } | null>(null);
  const create = useMutation({
    mutationFn: () =>
      api<{ token: string; details: EnrolmentToken }>("/endpoints/enrolment-tokens", {
        method: "POST",
        body: { kind: "collector", label, valid_hours: 24, max_uses: 1 },
      }),
    onSuccess: (res) => {
      setCreated(res);
      queryClient.invalidateQueries({ queryKey: orgKey });
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
      title={created ? "Install the network collector" : "Add a network collector"}
      description={
        created
          ? `Token valid until ${formatDateTime(created.details.expires_at)}.`
          : "The collector runs inside your office network and forwards firewall logs, intrusion alerts and device reachability over an outbound HTTPS connection."
      }
      footer={
        created ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button loading={create.isPending} onClick={() => create.mutate()} disabled={!label.trim()}>
              Create token
            </Button>
          </>
        )
      }
    >
      {created ? (
        <Instructions token={created.token} />
      ) : (
        <div className="space-y-4">
          {create.isError && <Callout tone="critical">{errorMessage(create.error)}</Callout>}
          <Field label="Location name" htmlFor="col-label" hint="For example the office or branch where it runs.">
            <Input id="col-label" value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
        </div>
      )}
    </Dialog>
  );
}
