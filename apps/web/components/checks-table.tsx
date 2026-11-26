"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CirclePlay } from "lucide-react";
import Link from "next/link";
import { AssetIcon } from "@/components/asset-badges";
import { CheckStatusBadge } from "@/components/monitoring-ui";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { AGENT_CHECK_TYPES, CHECK_TYPES, INTERVALS } from "@/lib/labels";
import type { Check } from "@/lib/types";

export function CheckRow({ check, showAsset = true }: { check: Check; showAsset?: boolean }) {
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const agentDriven = AGENT_CHECK_TYPES.has(check.check_type);
  const manage = can("monitoring:manage") && !agentDriven;

  const update = useMutation({
    mutationFn: (body: Partial<Pick<Check, "enabled" | "interval_minutes">>) =>
      api<Check>(`/monitoring/checks/${check.id}`, { method: "PATCH", body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: orgKey }),
    onError: (err) => toast("error", errorMessage(err)),
  });
  const run = useMutation({
    mutationFn: () => api<Check>(`/monitoring/checks/${check.id}/run`, { method: "POST" }),
    onSuccess: () => {
      toast("success", "Check queued. Results appear within a minute.");
      setTimeout(() => queryClient.invalidateQueries({ queryKey: orgKey }), 15000);
    },
    onError: (err) => toast("error", errorMessage(err)),
  });

  return (
    <tr className={check.enabled ? undefined : "opacity-60"}>
      {showAsset && (
        <Td>
          {check.asset && (
            <Link href={`/assets/${check.asset.id}`} className="flex min-w-44 items-center gap-2.5 hover:text-primary-text">
              <AssetIcon type={check.asset.type} className="size-4 text-subtle" />
              <span className="min-w-0">
                <span className="block truncate font-medium">{check.asset.name}</span>
                <span className="block truncate font-mono text-xs text-subtle">{check.asset.identifier}</span>
              </span>
            </Link>
          )}
        </Td>
      )}
      <Td className="min-w-40">
        <span className="block font-medium whitespace-nowrap" title={CHECK_TYPES[check.check_type]?.description}>
          {CHECK_TYPES[check.check_type]?.label ?? check.check_type}
        </span>
      </Td>
      <Td>
        <CheckStatusBadge status={check.last_status} enabled={check.enabled} />
        {check.last_summary && (
          <span className="mt-1 block max-w-56 truncate text-xs text-muted" title={check.last_summary}>
            {check.last_summary}
          </span>
        )}
      </Td>
      <Td className="whitespace-nowrap text-muted">{timeAgo(check.last_run_at)}</Td>
      <Td>
        {agentDriven ? (
          <span className="text-sm text-muted">Reported by agent</span>
        ) : manage ? (
          <Select
            aria-label="Frequency"
            value={check.interval_minutes}
            onChange={(e) => update.mutate({ interval_minutes: Number(e.target.value) })}
            className="h-9 w-37 min-w-37"
          >
            {INTERVALS.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </Select>
        ) : (
          <span className="text-sm text-muted">
            {INTERVALS.find((i) => i.value === check.interval_minutes)?.label}
          </span>
        )}
      </Td>
      {can("monitoring:manage") && !manage && <Td />}
      {manage && (
        <Td className="text-right whitespace-nowrap">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => run.mutate()}
            disabled={!check.enabled}
            loading={run.isPending}
            title="Run now"
          >
            <CirclePlay className="size-4" /> Run now
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => update.mutate({ enabled: !check.enabled })}
          >
            {check.enabled ? "Turn off" : "Turn on"}
          </Button>
        </Td>
      )}
    </tr>
  );
}

export function ChecksTable({ checks, showAsset = true }: { checks: Check[]; showAsset?: boolean }) {
  const { can } = useSession();
  return (
    <Table>
      <thead>
        <tr>
          {showAsset && <Th>Asset</Th>}
          <Th>Check</Th>
          <Th>Result</Th>
          <Th>Last run</Th>
          <Th>Frequency</Th>
          {can("monitoring:manage") && (
            <Th>
              <span className="sr-only">Actions</span>
            </Th>
          )}
        </tr>
      </thead>
      <tbody>
        {checks.map((c) => (
          <CheckRow key={c.id} check={c} showAsset={showAsset} />
        ))}
      </tbody>
    </Table>
  );
}
