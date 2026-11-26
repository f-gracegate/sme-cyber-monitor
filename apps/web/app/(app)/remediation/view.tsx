"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlarmClock, CircleCheck, ListTodo, Timer, Wrench } from "lucide-react";
import Link from "next/link";
import { TaskRow } from "@/components/incident-ui";
import { ChipFilter } from "@/components/monitoring-ui";
import { Pager } from "@/components/pager";
import { useOrgKey, useSession } from "@/components/session";
import { Callout, Card, EmptyState, PageHeader, Skeleton, StatCard, cn } from "@/components/ui";
import { api } from "@/lib/api";
import { TASK_STATUS } from "@/lib/labels";
import type { Page, RemediationSummary, Task } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";

const PAGE_SIZE = 50;
const OPEN = ["open", "in_progress", "done"];
const STATUS_OPTIONS = Object.entries(TASK_STATUS).map(([value, m]) => ({ value, label: m.label }));
const VIEWS = [
  { value: "all", label: "All tasks" },
  { value: "mine", label: "Assigned to me" },
  { value: "overdue", label: "Overdue" },
];

export function View() {
  const { can } = useSession();
  const team = can("remediation:read");
  const url = useUrlState();
  const view = team ? url.get("view") || "all" : "mine";
  const chosen = url.getAll("status");
  const status = chosen.length ? chosen : OPEN;

  const summary = useQuery({
    queryKey: useOrgKey("remediation-summary"),
    queryFn: () => api<RemediationSummary>("/remediation/summary"),
    enabled: team,
  });
  const { data, isPending } = useQuery({
    queryKey: useOrgKey("remediation-tasks", { view, status, page: url.page }),
    queryFn: () =>
      api<Page<Task>>("/remediation-tasks", {
        query: {
          status,
          mine: view === "mine" || undefined,
          overdue: view === "overdue" || undefined,
          page: url.page,
          page_size: PAGE_SIZE,
        },
      }),
    placeholderData: keepPreviousData,
  });
  const s = summary.data;

  return (
    <>
      <PageHeader
        title={team ? "Remediation" : "My tasks"}
        description={
          team
            ? "Who is fixing what, and by when. Fixes for monitored problems are verified automatically once monitoring confirms they're gone."
            : "Security tasks your team has asked you to do."
        }
      />
      {team && (
        <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Open tasks" value={s ? s.open + s.in_progress : "–"} hint={s ? `${s.in_progress} in progress` : undefined} icon={<ListTodo className="size-4" />} tone="primary" />
          <StatCard
            label="Overdue"
            value={s?.overdue ?? "–"}
            hint="Past their due date"
            icon={<AlarmClock className="size-4" />}
            tone={s && s.overdue > 0 ? "critical" : "success"}
          />
          <StatCard
            label="Fixed on time"
            value={s?.on_time_rate == null ? "–" : `${s.on_time_rate}%`}
            hint={s ? `${s.completed_30d} completed in 30 days` : undefined}
            icon={<CircleCheck className="size-4" />}
            tone="success"
          />
          <StatCard
            label="Median time to fix"
            value={s?.median_days_to_fix == null ? "–" : `${s.median_days_to_fix} d`}
            hint={s ? `${s.awaiting_verification} awaiting verification` : undefined}
            icon={<Timer className="size-4" />}
          />
        </div>
      )}
      {team && s && s.unassigned_urgent_findings > 0 && (
        <div className="mb-5">
          <Callout
            tone="high"
            title={`${s.unassigned_urgent_findings} critical or high finding${s.unassigned_urgent_findings === 1 ? " has" : "s have"} no one fixing ${s.unassigned_urgent_findings === 1 ? "it" : "them"}`}
            action={
              <Link href="/findings?severity=critical&severity=high" className="text-sm font-medium underline">
                Review findings
              </Link>
            }
          >
            Open each finding and use &ldquo;Assign fix&rdquo; to give it an owner and a deadline.
          </Callout>
        </div>
      )}
      <Card padded={false}>
        <div className="space-y-3 border-b border-border p-4">
          {team && (
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="View">
              {VIEWS.map((v) => (
                <button
                  key={v.value}
                  role="tab"
                  aria-selected={view === v.value}
                  onClick={() => url.set({ view: v.value === "all" ? null : v.value })}
                  className={cn(
                    "rounded-full px-3 py-1 text-sm font-medium",
                    view === v.value ? "bg-primary text-white" : "text-muted hover:bg-surface-2 hover:text-fg",
                  )}
                >
                  {v.label}
                </button>
              ))}
            </div>
          )}
          <ChipFilter label="Status" options={STATUS_OPTIONS} selected={status} onChange={(next) => url.set({ status: next.length ? next : null })} />
        </div>
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-48" />
          </div>
        ) : !data?.items.length ? (
          <EmptyState
            icon={<Wrench className="size-5" />}
            title={view === "overdue" ? "Nothing overdue" : "No tasks"}
            description={
              team
                ? "Create tasks from a finding (“Assign fix”) or from an incident's response plan."
                : "You have no security tasks right now."
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border">
              {data.items.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </ul>
            <Pager page={url.page} total={data.total} pageSize={PAGE_SIZE} noun={["task", "tasks"]} onPage={(p) => url.set({ page: String(p) }, true)} />
          </>
        )}
      </Card>
    </>
  );
}
