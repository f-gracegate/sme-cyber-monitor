"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Bell, ChevronRight } from "lucide-react";
import Link from "next/link";
import { AssetIcon } from "@/components/asset-badges";
import {
  AlertStatusBadge,
  ChipFilter,
  SeverityBadge,
  severityBarClass,
} from "@/components/monitoring-ui";
import { Pager } from "@/components/pager";
import { useOrgKey } from "@/components/session";
import { Card, EmptyState, PageHeader, Skeleton, cn } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { ALERT_STATUS, SEVERITIES } from "@/lib/labels";
import type { Alert, Page } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";

const PAGE_SIZE = 25;
const OPEN = ["new", "acknowledged", "investigating"];
const STATUS_OPTIONS = Object.entries(ALERT_STATUS).map(([value, m]) => ({ value, label: m.label }));

export function View() {
  const url = useUrlState();
  const severity = url.getAll("severity");
  const chosen = url.getAll("status");
  const status = chosen.length ? chosen : OPEN;

  const { data, isPending } = useQuery({
    queryKey: useOrgKey("alerts", { severity, status, page: url.page }),
    queryFn: () =>
      api<Page<Alert>>("/alerts", {
        query: { severity, status, page: url.page, page_size: PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Problems that need someone's attention. Repeats of the same issue are grouped into one alert, and alerts close automatically when monitoring sees the problem fixed."
      />
      <Card padded={false}>
        <div className="space-y-3 border-b border-border p-4">
          <ChipFilter label="Severity" options={SEVERITIES} selected={severity} onChange={(next) => url.set({ severity: next })} />
          <ChipFilter
            label="Status"
            options={STATUS_OPTIONS}
            selected={status}
            onChange={(next) => url.set({ status: next.length ? next : null })}
          />
        </div>
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-48" />
          </div>
        ) : !data?.items.length ? (
          <EmptyState
            icon={<Bell className="size-5" />}
            title="No alerts"
            description={
              status.join() === OPEN.join() && !severity.length
                ? "Nothing needs attention right now."
                : "No alerts match these filters."
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border">
              {data.items.map((a) => (
                <li key={a.id}>
                  <Link href={`/alerts/${a.id}`} className="group flex items-stretch gap-4 px-4 py-3.5 hover:bg-surface-2/60">
                    <span className={cn("w-1 shrink-0 rounded-full", severityBarClass(a.severity))} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-fg group-hover:text-primary-text">{a.title}</span>
                        <SeverityBadge severity={a.severity} />
                        <AlertStatusBadge status={a.status} />
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                        {a.asset && (
                          <span className="inline-flex items-center gap-1.5">
                            <AssetIcon type={a.asset.type} className="size-3.5" /> {a.asset.name}
                          </span>
                        )}
                        <span title={formatDateTime(a.first_seen_at)}>Raised {timeAgo(a.first_seen_at)}</span>
                        {a.occurrences > 1 && <span>Seen {a.occurrences}×, last {timeAgo(a.last_seen_at)}</span>}
                      </span>
                    </span>
                    <ChevronRight className="size-4 shrink-0 self-center text-subtle" />
                  </Link>
                </li>
              ))}
            </ul>
            <Pager page={url.page} total={data.total} pageSize={PAGE_SIZE} noun={["alert", "alerts"]} onPage={(p) => url.set({ page: String(p) }, true)} />
          </>
        )}
      </Card>
    </>
  );
}
