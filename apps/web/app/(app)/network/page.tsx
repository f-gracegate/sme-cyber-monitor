"use client";

import { useQuery } from "@tanstack/react-query";
import { Network, Plus, Radar, RadioTower, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AssetIcon } from "@/components/asset-badges";
import { CollectorDialog } from "@/components/collector-dialog";
import { EventsList } from "@/components/events-list";
import { SeverityBadge } from "@/components/monitoring-ui";
import { useOrgKey, useSession } from "@/components/session";
import {
  Badge,
  Button,
  ButtonLink,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  Skeleton,
  StatCard,
  Table,
  Td,
  Th,
  cn,
} from "@/components/ui";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { CAPABILITIES, assetTypeLabel } from "@/lib/labels";
import type { Collector, NetworkDevice, NetworkSummary } from "@/lib/types";

function bytes(n: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

const AVAILABILITY: Record<NetworkDevice["availability"], { label: string; tone: "success" | "critical" | "neutral" | "warning" }> = {
  reachable: { label: "Reachable", tone: "success" },
  unreachable: { label: "Unreachable", tone: "critical" },
  not_probed: { label: "Not checked yet", tone: "neutral" },
  awaiting_authorisation: { label: "Awaiting authorisation", tone: "warning" },
};

function CollectorsCard({ collectors }: { collectors: Collector[] }) {
  return (
    <Card padded={false}>
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Collectors</h2>
        <p className="text-[13px] text-muted">On-site components forwarding network telemetry.</p>
      </div>
      <Table>
        <thead>
          <tr>
            <Th>Collector</Th>
            <Th>Status</Th>
            <Th>Inputs</Th>
            <Th>Last heartbeat</Th>
            <Th>Queue</Th>
            <Th>Events (24h)</Th>
          </tr>
        </thead>
        <tbody>
          {collectors.map((c) => (
            <tr key={c.id}>
              <Td>
                <Link href={`/assets/${c.asset_id}`} className="block hover:text-primary-text">
                  <span className="block font-medium">{c.name}</span>
                  <span className="block text-xs text-subtle">
                    {c.hostname} · v{c.version}
                  </span>
                </Link>
              </Td>
              <Td>
                <Badge tone={c.online ? "success" : "high"} dot>
                  {c.online ? "Online" : "Offline"}
                </Badge>
              </Td>
              <Td>
                <div className="flex max-w-xs flex-wrap gap-1">
                  {c.capabilities.map((cap) => (
                    <Badge key={cap} tone={cap === "suricata" || cap === "zeek" ? "primary" : "neutral"}>
                      {CAPABILITIES[cap] ?? cap}
                    </Badge>
                  ))}
                </div>
              </Td>
              <Td className="whitespace-nowrap text-muted">{timeAgo(c.last_seen_at)}</Td>
              <Td className="tabular-nums">{c.queue_depth ?? "—"}</Td>
              <Td className="tabular-nums">{c.events_24h}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function DevicesCard({ devices }: { devices: NetworkDevice[] }) {
  const { can } = useSession();
  return (
    <Card padded={false}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold">Firewalls, routers and switches</h2>
          <p className="text-[13px] text-muted">Reachability is checked from your collector every minute.</p>
        </div>
        {can("assets:write") && (
          <ButtonLink href="/assets?new=1" variant="secondary" size="sm">
            <Plus className="size-4" /> Add device
          </ButtonLink>
        )}
      </div>
      {devices.length === 0 ? (
        <EmptyState
          icon={<Network className="size-5" />}
          title="No network devices registered"
          description="Add your firewall, routers and switches as assets, using each device's management IP address as its identifier."
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Device</Th>
              <Th>Type</Th>
              <Th>Availability</Th>
              <Th>Latency</Th>
              <Th>Last seen</Th>
              <Th>Events (24h)</Th>
              <Th>Open findings</Th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => {
              const a = AVAILABILITY[d.availability];
              return (
                <tr key={d.id} className="hover:bg-surface-2/60">
                  <Td>
                    <Link href={`/assets/${d.id}`} className="flex items-center gap-2.5 hover:text-primary-text">
                      <AssetIcon type={d.type} className="size-4 text-subtle" />
                      <span>
                        <span className="block font-medium">{d.name}</span>
                        <span className="block font-mono text-xs text-subtle">{d.identifier}</span>
                      </span>
                    </Link>
                  </Td>
                  <Td className="text-muted">{assetTypeLabel(d.type)}</Td>
                  <Td>
                    <Badge tone={a.tone} dot>
                      {a.label}
                    </Badge>
                  </Td>
                  <Td className="tabular-nums text-muted">{d.latency_ms != null ? `${d.latency_ms} ms` : "—"}</Td>
                  <Td className="whitespace-nowrap text-muted">{timeAgo(d.last_seen_at)}</Td>
                  <Td className="tabular-nums">{d.events_24h}</Td>
                  <Td className={cn("tabular-nums", d.open_findings ? "font-medium text-critical-text" : "text-subtle")}>
                    {d.open_findings}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

function IntrusionCard({ s }: { s: NetworkSummary }) {
  if (!s.sensor_deployed) {
    return (
      <Card>
        <CardHeader title="Intrusion detection and traffic" />
        <Callout tone="info" icon={<Radar className="size-4" />} title="No network sensor deployed">
          Traffic analysis and intrusion detection need a Suricata or Zeek sensor on a mirrored
          switch port, connected to your collector. Until then, packet inspection isn&apos;t
          running and nothing here is shown as protected. Firewall logs and reachability checks
          still work without a sensor.
        </Callout>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader title="Intrusion detection (24 hours)" description="Alerts from your network sensor." />
      <div className="mb-4 flex flex-wrap gap-2">
        {(["high", "medium", "low"] as const).map((sev) => (
          <span key={sev} className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
            <SeverityBadge severity={sev} />
            <span className="font-semibold tabular-nums">{s.ids_alerts_24h[sev] ?? 0}</span>
          </span>
        ))}
      </div>
      {s.top_signatures.length > 0 ? (
        <ul className="divide-y divide-border rounded-[var(--radius-control)] border border-border text-sm">
          {s.top_signatures.map((sig) => (
            <li key={sig.name} className="flex items-center gap-3 px-3 py-2">
              <SeverityBadge severity={sig.severity} />
              <span className="min-w-0 flex-1 truncate">{sig.name}</span>
              <span className="tabular-nums text-muted">{sig.count}×</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">No intrusion alerts in the last 24 hours.</p>
      )}
      {s.traffic && (
        <div className="mt-5">
          <h3 className="mb-2 text-xs font-medium tracking-wide text-subtle uppercase">
            Traffic (last {Math.round(s.traffic.window_seconds / 60) || 1} min)
          </h3>
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-subtle">Connections</dt>
              <dd className="font-semibold tabular-nums">{s.traffic.connections}</dd>
            </div>
            <div>
              <dt className="text-subtle">Download</dt>
              <dd className="font-semibold tabular-nums">{bytes(s.traffic.bytes_in)}</dd>
            </div>
            <div>
              <dt className="text-subtle">Upload</dt>
              <dd className="font-semibold tabular-nums">{bytes(s.traffic.bytes_out)}</dd>
            </div>
          </dl>
        </div>
      )}
    </Card>
  );
}

export default function NetworkPage() {
  const { can } = useSession();
  const [adding, setAdding] = useState(false);
  const [tab, setTab] = useState<"overview" | "events">("overview");
  const summary = useQuery({
    queryKey: useOrgKey("network", "summary"),
    queryFn: () => api<NetworkSummary>("/network/summary"),
    refetchInterval: 30_000,
  });
  const collectors = useQuery({
    queryKey: useOrgKey("network", "collectors"),
    queryFn: () => api<Collector[]>("/network/collectors"),
    refetchInterval: 30_000,
  });
  const devices = useQuery({
    queryKey: useOrgKey("network", "devices"),
    queryFn: () => api<NetworkDevice[]>("/network/devices"),
    refetchInterval: 30_000,
  });

  const s = summary.data;
  const allowance = s?.collector_allowance;
  const canAdd = can("monitoring:manage") && (allowance === null || (allowance ?? 0) > (s?.collectors_total ?? 0));

  return (
    <>
      <PageHeader
        title="Network"
        description="Firewall and router logs, device reachability and intrusion detection from collectors inside your network."
        actions={
          canAdd && (
            <Button onClick={() => setAdding(true)}>
              <Plus className="size-4" /> Add collector
            </Button>
          )
        }
      />

      {!s ? (
        <Skeleton className="h-32" />
      ) : (
        <>
          {s.collectors_total === 0 && allowance === 0 && (
            <div className="mb-5">
              <Callout
                tone="info"
                title="Network monitoring is part of the Professional plan"
                action={
                  <ButtonLink href="/settings/subscription" variant="secondary" size="sm">
                    View plans
                  </ButtonLink>
                }
              >
                Your current plan covers websites, domains and devices with agents. Upgrade to add
                an on-site network collector.
              </Callout>
            </div>
          )}
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Collectors online"
              value={`${s.collectors_online} / ${s.collectors_total}`}
              hint={allowance === null ? "Unlimited on your plan" : `${allowance} included in your plan`}
              icon={<RadioTower className="size-4" />}
              tone="primary"
            />
            <StatCard
              label="Devices reachable"
              value={`${s.devices_reachable} / ${s.devices_total}`}
              hint={s.devices_unreachable ? `${s.devices_unreachable} unreachable` : `${s.devices_not_probed} not checked yet`}
              icon={<ShieldCheck className="size-4" />}
              tone={s.devices_unreachable ? "critical" : "success"}
            />
            <StatCard
              label="Blocked connections (24h)"
              value={s.firewall_denies_24h.toLocaleString()}
              hint={`${s.config_changes_24h} configuration change(s)`}
              icon={<Network className="size-4" />}
              tone="info"
            />
            <StatCard
              label="Intrusion alerts (24h)"
              value={s.sensor_deployed ? Object.values(s.ids_alerts_24h).reduce((a, b) => a + b, 0) : "—"}
              hint={s.sensor_deployed ? "From your network sensor" : "No network sensor deployed"}
              icon={<ShieldAlert className="size-4" />}
              tone="high"
            />
          </div>
        </>
      )}

      <div className="mb-4 flex gap-1 border-b border-border" role="tablist">
        {(["overview", "events"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn("-mb-px border-b-2 px-3 py-2.5 text-sm", tab === t ? "border-primary font-medium text-primary-text" : "border-transparent text-muted hover:text-fg")}
          >
            {t === "overview" ? "Overview" : "Network events"}
          </button>
        ))}
      </div>

      {tab === "events" ? (
        <Card padded={false}>
          <EventsList showAsset category="network" />
        </Card>
      ) : (
        <div className="space-y-6">
          {collectors.data && collectors.data.length > 0 ? (
            <CollectorsCard collectors={collectors.data} />
          ) : (
            <Card>
              <EmptyState
                icon={<RadioTower className="size-5" />}
                title="No collectors yet"
                description="A collector is a small program on an always-on machine in your office. It receives firewall and router logs and checks that your network devices are up."
                action={
                  canAdd && (
                    <Button onClick={() => setAdding(true)}>
                      <Plus className="size-4" /> Add collector
                    </Button>
                  )
                }
              />
            </Card>
          )}
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            {devices.data ? <DevicesCard devices={devices.data} /> : <Skeleton className="h-48" />}
            {s && <IntrusionCard s={s} />}
          </div>
        </div>
      )}

      {adding && <CollectorDialog open onClose={() => setAdding(false)} />}
    </>
  );
}
