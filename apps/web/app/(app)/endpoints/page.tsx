"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Laptop, Plus, Wifi, WifiOff, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AssetIcon } from "@/components/asset-badges";
import { EnrolDialog } from "@/components/enrol-dialog";
import { OnlineBadge } from "@/components/endpoint-ui";
import { EventsList } from "@/components/events-list";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Skeleton,
  StatCard,
  Table,
  Td,
  Th,
  cn,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { AGENT_SOURCE } from "@/lib/labels";
import type { Endpoint, EndpointSummary, EnrolmentToken } from "@/lib/types";

function ActiveTokens() {
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("enrolment-tokens");
  const { data } = useQuery({
    queryKey: key,
    queryFn: () => api<EnrolmentToken[]>("/endpoints/enrolment-tokens"),
    enabled: can("monitoring:manage"),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/endpoints/enrolment-tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      toast("success", "Token revoked.");
    },
    onError: (err) => toast("error", errorMessage(err)),
  });
  if (!data?.length) return null;
  return (
    <Card padded={false} className="mt-6">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Active enrolment tokens</h2>
        <p className="text-[13px] text-muted">Revoke any token you no longer need.</p>
      </div>
      <ul className="divide-y divide-border">
        {data.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
            <code className="font-mono text-xs">{t.token_hint}…</code>
            <span className="min-w-0 flex-1 text-muted">
              {t.label ?? `${t.asset_type} token`} · {t.uses}/{t.max_uses} used · expires {formatDate(t.expires_at)}
            </span>
            <Button variant="ghost" size="sm" onClick={() => revoke.mutate(t.id)}>
              <X className="size-4" /> Revoke
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function inventoryFacts(e: Endpoint) {
  const inv = e.inventory as Record<string, unknown>;
  const flag = (v: unknown, on: string, off: string) => (v === true ? on : v === false ? off : null);
  return [
    flag(inv.firewall_enabled, "Firewall on", "Firewall OFF"),
    flag(inv.antivirus_enabled, "AV on", "AV OFF"),
    flag(inv.disk_encrypted, "Encrypted", "Not encrypted"),
  ].filter(Boolean) as string[];
}

export default function EndpointsPage() {
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [enrolling, setEnrolling] = useState(false);
  const [tab, setTab] = useState<"devices" | "events">("devices");

  const summary = useQuery({
    queryKey: useOrgKey("endpoints", "summary"),
    queryFn: () => api<EndpointSummary>("/endpoints/summary"),
    refetchInterval: 30_000,
  });
  const endpoints = useQuery({
    queryKey: useOrgKey("endpoints", "list"),
    queryFn: () => api<Endpoint[]>("/endpoints"),
    refetchInterval: 30_000,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api<Endpoint>(`/endpoints/${id}/revoke`, { method: "POST" }),
    onSuccess: (e) => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", `${e.hostname} can no longer send data. Re-enrol it to resume monitoring.`);
    },
    onError: (err) => toast("error", errorMessage(err)),
  });

  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Endpoints"
        description="Computers and servers reporting through a monitoring agent: health, sign-in activity and security events."
        actions={
          can("monitoring:manage") && (
            <Button onClick={() => setEnrolling(true)}>
              <Plus className="size-4" /> Add devices
            </Button>
          )
        }
      />

      {s && (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Online" value={`${s.online} / ${s.total}`} hint="Agents checked in within 15 minutes" icon={<Wifi className="size-4" />} tone="success" />
          <StatCard label="Offline" value={s.offline} hint="Coverage gaps: we can't see these devices" icon={<WifiOff className="size-4" />} tone="high" />
          <StatCard label="Devices with issues" value={s.with_issues} hint="At least one open finding" tone="warning" />
          <StatCard label="Security events (24h)" value={s.events_24h} hint="From all agents" tone="info" />
        </div>
      )}

      <div className="mb-4 flex gap-1 border-b border-border" role="tablist">
        {(["devices", "events"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn("-mb-px border-b-2 px-3 py-2.5 text-sm", tab === t ? "border-primary font-medium text-primary-text" : "border-transparent text-muted hover:text-fg")}
          >
            {t === "devices" ? "Devices" : "Security events"}
          </button>
        ))}
      </div>

      {tab === "events" ? (
        <Card padded={false}>
          <EventsList showAsset />
        </Card>
      ) : (
        <Card padded={false}>
          {endpoints.isPending ? (
            <div className="p-4">
              <Skeleton className="h-40" />
            </div>
          ) : !endpoints.data?.length ? (
            <EmptyState
              icon={<Laptop className="size-5" />}
              title="No devices are reporting yet"
              description="Install the monitoring agent on your computers and servers, or connect your Wazuh manager. Devices appear here as soon as they check in."
              action={
                can("monitoring:manage") && (
                  <Button onClick={() => setEnrolling(true)}>
                    <Plus className="size-4" /> Add devices
                  </Button>
                )
              }
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Device</Th>
                  <Th>Operating system</Th>
                  <Th>Agent</Th>
                  <Th>Status</Th>
                  <Th>Last heartbeat</Th>
                  <Th>Group</Th>
                  <Th>Events (24h)</Th>
                  <Th>Open alerts</Th>
                  {can("monitoring:manage") && (
                    <Th>
                      <span className="sr-only">Actions</span>
                    </Th>
                  )}
                </tr>
              </thead>
              <tbody>
                {endpoints.data.map((e) => (
                  <tr key={e.id} className="hover:bg-surface-2/60">
                    <Td>
                      <Link href={`/assets/${e.asset.id}`} className="flex min-w-44 items-center gap-2.5 hover:text-primary-text">
                        <AssetIcon type={e.asset.type} className="size-4 text-subtle" />
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{e.hostname}</span>
                          <span className="block truncate text-xs text-subtle">{inventoryFacts(e).join(" · ") || e.last_ip || "—"}</span>
                        </span>
                      </Link>
                    </Td>
                    <Td className="whitespace-nowrap text-muted">{[e.os_name, e.os_version].filter(Boolean).join(" ") || "—"}</Td>
                    <Td className="whitespace-nowrap text-muted">
                      {AGENT_SOURCE[e.source]}
                      {e.source === "smecm_agent" && e.agent_version ? ` ${e.agent_version}` : ""}
                    </Td>
                    <Td>
                      <OnlineBadge endpoint={e} />
                    </Td>
                    <Td className="whitespace-nowrap text-muted">{timeAgo(e.last_seen_at)}</Td>
                    <Td className="text-muted">{e.asset.department_name ?? "—"}</Td>
                    <Td className="tabular-nums">{e.events_24h}</Td>
                    <Td>
                      {e.open_alerts ? (
                        <Link href={`/alerts?status=new&status=acknowledged&status=investigating`} className="font-medium text-critical-text">
                          {e.open_alerts}
                        </Link>
                      ) : (
                        <span className="text-subtle">0</span>
                      )}
                    </Td>
                    {can("monitoring:manage") && (
                      <Td className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (window.confirm(`Revoke the agent on ${e.hostname}? It will stop sending data.`)) revoke.mutate(e.id);
                          }}
                        >
                          Revoke
                        </Button>
                      </Td>
                    )}
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {tab === "devices" && <ActiveTokens />}
      {enrolling && <EnrolDialog open onClose={() => setEnrolling(false)} />}
    </>
  );
}
