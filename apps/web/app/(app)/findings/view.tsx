"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ScanSearch, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { FindingList } from "@/components/finding-list";
import { ChipFilter } from "@/components/monitoring-ui";
import { Pager } from "@/components/pager";
import { useOrgKey } from "@/components/session";
import { Card, EmptyState, Input, PageHeader, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { CHECK_TYPES, FINDING_STATUS, SEVERITIES } from "@/lib/labels";
import type { Finding, Page } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";

const PAGE_SIZE = 25;

export function View() {
  const url = useUrlState();
  const severity = url.getAll("severity");
  const status = url.get("status") || "open";
  const checkType = url.get("check_type");
  const q = url.get("q");
  const [search, setSearch] = useState(q);

  useEffect(() => {
    if (search === q) return;
    const t = setTimeout(() => url.set({ q: search || null }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const { data, isPending } = useQuery({
    queryKey: useOrgKey("findings", { severity, status, checkType, q, page: url.page }),
    queryFn: () =>
      api<Page<Finding>>("/findings", {
        query: { severity, status, check_type: checkType, q, page: url.page, page_size: PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Findings"
        description="Security weaknesses and misconfigurations found by monitoring, most serious first. Each one explains what's wrong, why it matters and how to fix it."
      />
      <Card padded={false}>
        <div className="space-y-3 border-b border-border p-4">
          <div className="flex flex-col gap-3 lg:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
              <Input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search findings or assets"
                className="pl-9"
                aria-label="Search findings"
              />
            </div>
            <Select aria-label="Status" value={status} onChange={(e) => url.set({ status: e.target.value === "open" ? null : e.target.value })} className="lg:w-44">
              {Object.entries(FINDING_STATUS).map(([v, m]) => (
                <option key={v} value={v}>
                  {m.label}
                </option>
              ))}
            </Select>
            <Select aria-label="Check" value={checkType} onChange={(e) => url.set({ check_type: e.target.value || null })} className="lg:w-48">
              <option value="">All checks</option>
              {Object.entries(CHECK_TYPES).map(([v, m]) => (
                <option key={v} value={v}>
                  {m.label}
                </option>
              ))}
            </Select>
          </div>
          <ChipFilter label="Severity" options={SEVERITIES} selected={severity} onChange={(next) => url.set({ severity: next })} />
        </div>
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-48" />
          </div>
        ) : !data?.items.length ? (
          <EmptyState
            icon={<ScanSearch className="size-5" />}
            title={status === "open" && !severity.length && !q ? "No open findings" : "No findings match these filters"}
            description={
              status === "open"
                ? "Nothing currently needs fixing on your monitored assets. Assets that aren't monitored yet can't produce findings, so check your monitoring coverage too."
                : undefined
            }
          />
        ) : (
          <>
            <FindingList findings={data.items} />
            <Pager page={url.page} total={data.total} pageSize={PAGE_SIZE} noun={["finding", "findings"]} onPage={(p) => url.set({ page: String(p) }, true)} />
          </>
        )}
      </Card>
    </>
  );
}
