"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { useState } from "react";
import { EvidenceList, SeverityBadge } from "@/components/monitoring-ui";
import { Pager } from "@/components/pager";
import { useOrgKey } from "@/components/session";
import { EmptyState, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { EVENT_TYPES } from "@/lib/labels";
import type { Page, SecurityEvent } from "@/lib/types";

const PAGE_SIZE = 50;

export function EventsList({ assetId, showAsset = false }: { assetId?: string; showAsset?: boolean }) {
  const [eventType, setEventType] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const { data, isPending } = useQuery({
    queryKey: useOrgKey("events", { assetId, eventType, page }),
    queryFn: () =>
      api<Page<SecurityEvent>>("/endpoints/events", {
        query: { asset_id: assetId, event_type: eventType, page, page_size: PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <div>
      <div className="border-b border-border p-4">
        <Select
          aria-label="Event type"
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value);
            setPage(1);
          }}
          className="sm:w-60"
        >
          <option value="">All event types</option>
          {Object.entries(EVENT_TYPES).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      </div>
      {isPending ? (
        <div className="p-4">
          <Skeleton className="h-40" />
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<Activity className="size-5" />}
          title="No security events"
          description="Sign-in attempts, malware detections and other events from monitoring agents appear here. Events are kept for 30 days."
        />
      ) : (
        <>
          <ul className="divide-y divide-border">
            {data.items.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  onClick={() => setOpen(open === e.id ? null : e.id)}
                  aria-expanded={open === e.id}
                  className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left text-sm hover:bg-surface-2/60"
                >
                  <SeverityBadge severity={e.severity} />
                  <span className="font-medium">{EVENT_TYPES[e.event_type] ?? e.event_type}</span>
                  <span className="min-w-0 flex-1 truncate text-muted">
                    {e.summary}
                    {showAsset && e.asset_name ? ` · ${e.asset_name}` : ""}
                  </span>
                  {Boolean(e.data?.simulated) && (
                    <span className="rounded bg-warning-soft px-1.5 py-0.5 text-[11px] font-medium text-warning-text">TEST</span>
                  )}
                  <time className="text-xs text-subtle" dateTime={e.occurred_at} title={formatDateTime(e.occurred_at)}>
                    {timeAgo(e.occurred_at)}
                  </time>
                </button>
                {open === e.id && (
                  <div className="px-4 pb-4">
                    <EvidenceList evidence={e.data} />
                  </div>
                )}
              </li>
            ))}
          </ul>
          <Pager page={page} total={data.total} pageSize={PAGE_SIZE} noun={["event", "events"]} onPage={setPage} />
        </>
      )}
    </div>
  );
}
