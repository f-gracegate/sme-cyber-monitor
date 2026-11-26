"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronRight, Plus, Search, Siren } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { IncidentStatusBadge, incidentStatusOptions } from "@/components/incident-ui";
import { ChipFilter, SeverityBadge, severityBarClass } from "@/components/monitoring-ui";
import { Pager } from "@/components/pager";
import { ReportIncidentDialog } from "@/components/report-incident-dialog";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Card, EmptyState, Input, PageHeader, Skeleton, cn } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { INCIDENT_SOURCE, SEVERITIES, categoryName } from "@/lib/labels";
import type { Incident, Page } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";

const PAGE_SIZE = 25;
const ACTIVE = ["open", "investigating", "contained"];

export function View() {
  const { can } = useSession();
  const responder = can("incidents:read");
  const url = useUrlState();
  const severity = url.getAll("severity");
  const chosen = url.getAll("status");
  const status = chosen.length ? chosen : responder ? ACTIVE : [];
  const q = url.get("q");
  const [search, setSearch] = useState(q);
  const [reporting, setReporting] = useState(false);

  const { data, isPending } = useQuery({
    queryKey: useOrgKey("incidents", { severity, status, q, page: url.page }),
    queryFn: () =>
      api<Page<Incident>>("/incidents", {
        query: { severity, status, q, page: url.page, page_size: PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title={responder ? "Incidents" : "My incident reports"}
        description={
          responder
            ? "Security events that need a coordinated response. Incidents open automatically for critical alerts and repeated high-severity alerts, and staff can report what they notice."
            : "Something suspicious? Report it here and your security team will follow up. You can track the reports you've sent below."
        }
        actions={
          <Button onClick={() => setReporting(true)}>
            <Plus className="size-4" /> {can("incidents:manage") ? "Open incident" : "Report an incident"}
          </Button>
        }
      />
      <Card padded={false}>
        {responder && (
          <div className="space-y-3 border-b border-border p-4">
            <form
              className="relative max-w-sm"
              onSubmit={(e) => {
                e.preventDefault();
                url.set({ q: search.trim() || null });
              }}
            >
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
              <Input
                aria-label="Search incidents"
                placeholder="Search title or INC number"
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </form>
            <ChipFilter label="Severity" options={SEVERITIES.filter((s) => s.value !== "informational")} selected={severity} onChange={(next) => url.set({ severity: next })} />
            <ChipFilter
              label="Status"
              options={incidentStatusOptions}
              selected={status}
              onChange={(next) => url.set({ status: next.length ? next : null })}
            />
          </div>
        )}
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-48" />
          </div>
        ) : !data?.items.length ? (
          <EmptyState
            icon={<Siren className="size-5" />}
            title={responder ? "No incidents" : "You haven't reported anything"}
            description={
              responder
                ? status.join() === ACTIVE.join() && !severity.length && !q
                  ? "No active incidents. Critical alerts will open one automatically."
                  : "No incidents match these filters."
                : "If you notice a suspicious email, a lost device or anything odd, report it — early reports make a big difference."
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border">
              {data.items.map((inc) => (
                <li key={inc.id}>
                  <Link href={`/incidents/${inc.id}`} className="group flex items-stretch gap-4 px-4 py-3.5 hover:bg-surface-2/60">
                    <span className={cn("w-1 shrink-0 rounded-full", severityBarClass(inc.severity))} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[13px] text-muted">{inc.reference}</span>
                        <span className="font-medium text-fg group-hover:text-primary-text">{inc.title}</span>
                        <SeverityBadge severity={inc.severity} />
                        <IncidentStatusBadge status={inc.status} />
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                        <span>{categoryName(inc.category)}</span>
                        <span title={formatDateTime(inc.created_at)}>Opened {timeAgo(inc.created_at)}</span>
                        <span>{INCIDENT_SOURCE[inc.source]}</span>
                        <span>{inc.owner ? `Owner: ${inc.owner.name}` : <span className="text-high-text">No owner</span>}</span>
                        {inc.alert_count > 0 && <span>{inc.alert_count} alert{inc.alert_count === 1 ? "" : "s"}</span>}
                        {inc.open_tasks > 0 && <span>{inc.open_tasks} open task{inc.open_tasks === 1 ? "" : "s"}</span>}
                      </span>
                    </span>
                    <ChevronRight className="size-4 shrink-0 self-center text-subtle" />
                  </Link>
                </li>
              ))}
            </ul>
            <Pager page={url.page} total={data.total} pageSize={PAGE_SIZE} noun={["incident", "incidents"]} onPage={(p) => url.set({ page: String(p) }, true)} />
          </>
        )}
      </Card>
      {reporting && <ReportIncidentDialog open onClose={() => setReporting(false)} />}
    </>
  );
}
