"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ShieldQuestion } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChecksTable } from "@/components/checks-table";
import { useOrgKey } from "@/components/session";
import {
  ButtonLink,
  Callout,
  Card,
  EmptyState,
  PageHeader,
  Select,
  Skeleton,
  StatCard,
} from "@/components/ui";
import { api } from "@/lib/api";
import { CHECK_STATUS, CHECK_TYPES } from "@/lib/labels";
import type { Check, MonitoringSummary } from "@/lib/types";

export function View() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const status = params.get("status") ?? "";
  const checkType = params.get("check_type") ?? "";

  const summary = useQuery({
    queryKey: useOrgKey("monitoring", "summary"),
    queryFn: () => api<MonitoringSummary>("/monitoring/summary"),
    refetchInterval: 30_000,
  });
  const checks = useQuery({
    queryKey: useOrgKey("monitoring", "checks", { status, checkType }),
    queryFn: () =>
      api<Check[]>("/monitoring/checks", { query: { status, check_type: checkType } }),
    refetchInterval: 30_000,
  });

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }

  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Monitoring"
        description="Scheduled checks on your authorised websites and domains. Endpoint and network monitoring are added in later phases."
      />

      {s && (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Monitored assets"
            value={`${s.monitored_assets} / ${s.monitorable_assets}`}
            hint="Websites and domains with monitoring data"
            icon={<Activity className="size-4" />}
            tone="primary"
          />
          <StatCard
            label="Passing checks"
            value={s.by_status.ok ?? 0}
            hint={`of ${s.checks_enabled} active checks`}
            tone="success"
          />
          <StatCard
            label="Checks with issues"
            value={(s.by_status.warning ?? 0) + (s.by_status.failing ?? 0)}
            hint={`${s.by_status.failing ?? 0} failing`}
            tone="warning"
          />
          <StatCard
            label="Couldn't check"
            value={s.by_status.error ?? 0}
            hint="Coverage gaps, not good news"
            tone="high"
          />
        </div>
      )}

      {s && s.awaiting_authorisation > 0 && (
        <div className="mb-5">
          <Callout
            tone="warning"
            icon={<ShieldQuestion className="size-4" />}
            action={
              <ButtonLink href="/assets?monitoring_status=not_monitored" variant="secondary" size="sm">
                Review
              </ButtonLink>
            }
          >
            {s.awaiting_authorisation} website(s) or domain(s) can&apos;t be monitored until you
            prove you control them.
          </Callout>
        </div>
      )}

      <Card padded={false}>
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row">
          <Select
            aria-label="Result"
            value={status}
            onChange={(e) => setFilter("status", e.target.value)}
            className="sm:w-56"
          >
            <option value="">All results</option>
            {Object.entries(CHECK_STATUS).map(([v, m]) => (
              <option key={v} value={v}>
                {m.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Check type"
            value={checkType}
            onChange={(e) => setFilter("check_type", e.target.value)}
            className="sm:w-56"
          >
            <option value="">All checks</option>
            {Object.entries(CHECK_TYPES).map(([v, m]) => (
              <option key={v} value={v}>
                {m.label}
              </option>
            ))}
          </Select>
        </div>
        {checks.isPending ? (
          <div className="p-4">
            <Skeleton className="h-40" />
          </div>
        ) : !checks.data?.length ? (
          <EmptyState
            icon={<Activity className="size-5" />}
            title={status || checkType ? "No checks match these filters" : "No monitoring checks yet"}
            description="Checks are created automatically when you verify ownership of a website or domain."
            action={
              !status && !checkType && (
                <ButtonLink href="/assets?category=websites_domains" variant="secondary">
                  Go to websites & domains
                </ButtonLink>
              )
            }
          />
        ) : (
          <ChecksTable checks={checks.data} />
        )}
      </Card>
    </>
  );
}
