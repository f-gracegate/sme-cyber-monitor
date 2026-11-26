"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { CopyField } from "@/components/copy-field";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Callout, Card, CardHeader, Field, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import type { IntegrationKey } from "@/lib/types";

function ConfigSnippet({ apiKey }: { apiKey: string }) {
  const origin = typeof window === "undefined" ? "https://YOUR-SERVER" : window.location.origin;
  const text = `<integration>
  <name>custom-smecm</name>
  <hook_url>${origin}/api/v1/integrations/wazuh/alerts</hook_url>
  <api_key>${apiKey}</api_key>
  <level>3</level>
  <alert_format>json</alert_format>
</integration>`;
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-[var(--radius-control)] bg-navy p-3 pr-16 font-mono text-[12.5px] leading-relaxed text-slate-100 dark:bg-black/40">
        {text}
      </pre>
      <button
        type="button"
        onClick={() => navigator.clipboard?.writeText(text)}
        className="absolute top-2 right-2 rounded-md bg-white/10 px-2 py-1 text-xs text-slate-200 hover:bg-white/20"
      >
        Copy
      </button>
    </div>
  );
}

export default function IntegrationsPage() {
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("integration-keys");
  const [name, setName] = useState("Wazuh manager");
  const [created, setCreated] = useState<string | null>(null);

  const keys = useQuery({
    queryKey: key,
    queryFn: () => api<IntegrationKey[]>("/integrations/keys"),
    enabled: can("org:update"),
  });
  const create = useMutation({
    mutationFn: () =>
      api<{ key: string }>("/integrations/keys", { method: "POST", body: { name, kind: "wazuh" } }),
    onSuccess: (res) => {
      setCreated(res.key);
      queryClient.invalidateQueries({ queryKey: key });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/integrations/keys/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      toast("success", "Key revoked. The Wazuh manager can no longer send alerts with it.");
    },
    onError: (err) => toast("error", errorMessage(err)),
  });

  if (!can("org:update")) {
    return <Callout tone="info">Only owners and administrators can manage integrations.</Callout>;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Wazuh"
          description="Use Wazuh agents for full endpoint detection: malware, suspicious processes, Windows event analysis and file integrity. Your Wazuh manager forwards its alerts here, and each Wazuh agent appears as a monitored device."
        />
        {created ? (
          <div className="space-y-4">
            <CopyField label="Integration key" value={created} />
            <Callout tone="warning">Copy this key now. It won&apos;t be shown again.</Callout>
            <ol className="list-decimal space-y-2 pl-5 text-sm text-muted">
              <li>
                On the Wazuh manager, download the forwarding script to{" "}
                <code className="font-mono">/var/ossec/integrations/custom-smecm</code>, then run{" "}
                <code className="font-mono">chown root:wazuh</code> and <code className="font-mono">chmod 750</code> on it.
                <a href="/api/v1/agent/wazuh-integration" className="ml-1 text-primary-text underline">
                  Download script
                </a>
              </li>
              <li>
                Add this block to <code className="font-mono">/var/ossec/etc/ossec.conf</code> and restart the manager:
              </li>
            </ol>
            <ConfigSnippet apiKey={created} />
            <Button variant="secondary" onClick={() => setCreated(null)}>
              Done
            </Button>
          </div>
        ) : (
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Field label="Key name" htmlFor="key-name" className="flex-1">
              <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
              <KeyRound className="size-4" /> Create integration key
            </Button>
          </form>
        )}
        {create.isError && (
          <div className="mt-3">
            <Callout tone="critical">{errorMessage(create.error)}</Callout>
          </div>
        )}
      </Card>

      {(keys.data?.length ?? 0) > 0 && (
        <Card padded={false}>
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-[15px] font-semibold">Active keys</h2>
          </div>
          <ul className="divide-y divide-border">
            {keys.data!.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <span className="font-medium">{k.name}</span>
                <code className="font-mono text-xs text-subtle">smecm_int_{k.key_prefix}_…</code>
                <span className="min-w-0 flex-1 text-muted">
                  Created {formatDate(k.created_at)} · last used {timeAgo(k.last_used_at)}
                </span>
                <Button variant="ghost" size="sm" onClick={() => revoke.mutate(k.id)}>
                  <X className="size-4" /> Revoke
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
