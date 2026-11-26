"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus, Search, Server } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AssetIcon, CriticalityBadge, MonitoringBadge, RiskBadge } from "@/components/asset-badges";
import { AssetFormDialog } from "@/components/asset-form";
import { useOrgKey, useSession } from "@/components/session";
import {
  Button,
  Card,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  cn,
} from "@/components/ui";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { CATEGORIES, CRITICALITY, MONITORING_STATUS, assetTypeLabel } from "@/lib/labels";
import type { Asset, Page } from "@/lib/types";

const PAGE_SIZE = 25;

export function AssetInventory() {
  const { can } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const filters = {
    q: params.get("q") ?? "",
    category: params.get("category") ?? "",
    monitoring_status: params.get("monitoring_status") ?? "",
    criticality: params.get("criticality") ?? "",
    status: params.get("status") ?? "active",
    page: Number(params.get("page") ?? 1),
  };
  const [search, setSearch] = useState(filters.q);
  const creating = params.get("new") === "1" && can("assets:write");

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    const qs = next.toString();
    router.replace(`${pathname}${qs ? `?${qs}` : ""}`, { scroll: false });
  }

  // Debounce the search box into the URL.
  useEffect(() => {
    if (search === filters.q) return;
    const t = setTimeout(() => update({ q: search || null }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const key = useOrgKey("assets", filters);
  const { data, isPending, isFetching } = useQuery({
    queryKey: key,
    queryFn: () =>
      api<Page<Asset>>("/assets", {
        query: {
          q: filters.q,
          category: filters.category,
          monitoring_status: filters.monitoring_status,
          criticality: filters.criticality,
          status: filters.status,
          page: filters.page,
          page_size: PAGE_SIZE,
        },
      }),
    placeholderData: keepPreviousData,
  });

  const hasFilters = Boolean(
    filters.q || filters.category || filters.monitoring_status || filters.criticality,
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="Assets"
        description="Everything your business has registered for monitoring: websites, computers, servers, network devices and cloud services."
        actions={
          can("assets:write") && (
            <Button onClick={() => update({ new: "1" })}>
              <Plus className="size-4" /> Add asset
            </Button>
          )
        }
      />

      <Card padded={false}>
        <div className="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or identifier"
              className="pl-9"
              aria-label="Search assets"
            />
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:flex">
            <Select
              aria-label="Category"
              value={filters.category}
              onChange={(e) => update({ category: e.target.value || null })}
              className="lg:w-48"
            >
              <option value="">All categories</option>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Monitoring status"
              value={filters.monitoring_status}
              onChange={(e) => update({ monitoring_status: e.target.value || null })}
              className="lg:w-48"
            >
              <option value="">Any status</option>
              {Object.entries(MONITORING_STATUS).map(([value, m]) => (
                <option key={value} value={value}>
                  {m.label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Criticality"
              value={filters.criticality}
              onChange={(e) => update({ criticality: e.target.value || null })}
              className="lg:w-44"
            >
              <option value="">Any criticality</option>
              {CRITICALITY.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Show"
              value={filters.status}
              onChange={(e) => update({ status: e.target.value === "active" ? null : e.target.value })}
              className="lg:w-32"
            >
              <option value="active">Active</option>
              <option value="archived">Archived</option>
            </Select>
          </div>
        </div>

        {isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={<Server className="size-5" />}
            title={hasFilters ? "No assets match these filters" : filters.status === "archived" ? "No archived assets" : "No assets yet"}
            description={
              hasFilters
                ? "Try a different search or clear the filters."
                : "Start with your website or domain, then add the computers, servers and network devices you rely on."
            }
            action={
              hasFilters ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setSearch("");
                    update({ q: null, category: null, monitoring_status: null, criticality: null });
                  }}
                >
                  Clear filters
                </Button>
              ) : (
                can("assets:write") &&
                filters.status === "active" && (
                  <Button onClick={() => update({ new: "1" })}>
                    <Plus className="size-4" /> Add your first asset
                  </Button>
                )
              )
            }
          />
        ) : (
          <>
            {/* Desktop table */}
            <div className={cn("hidden md:block", isFetching && "opacity-70")}>
              <Table>
                <thead>
                  <tr>
                    <Th>Asset</Th>
                    <Th>Type</Th>
                    <Th>Department / owner</Th>
                    <Th>Criticality</Th>
                    <Th>Monitoring</Th>
                    <Th>Risk</Th>
                    <Th>Last seen</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((a) => (
                    <tr key={a.id} className="group hover:bg-surface-2/60">
                      <Td>
                        <Link href={`/assets/${a.id}`} className="flex items-center gap-3">
                          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted group-hover:bg-primary-soft group-hover:text-primary-text">
                            <AssetIcon type={a.type} />
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate font-medium text-fg group-hover:text-primary-text">
                              {a.name}
                            </span>
                            <span className="block max-w-xs truncate font-mono text-xs text-subtle">
                              {a.identifier}
                            </span>
                          </span>
                        </Link>
                      </Td>
                      <Td className="text-muted">{assetTypeLabel(a.type)}</Td>
                      <Td>
                        <span className="block text-fg">{a.department_name ?? "—"}</span>
                        <span className="block text-xs text-subtle">{a.owner_name ?? "No owner"}</span>
                      </Td>
                      <Td>
                        <CriticalityBadge level={a.criticality} />
                      </Td>
                      <Td>
                        <MonitoringBadge status={a.monitoring_status} />
                      </Td>
                      <Td>
                        <RiskBadge level={a.risk_level} />
                      </Td>
                      <Td className="text-muted">{timeAgo(a.last_seen_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>

            {/* Mobile cards */}
            <ul className="divide-y divide-border md:hidden">
              {data.items.map((a) => (
                <li key={a.id}>
                  <Link href={`/assets/${a.id}`} className="flex gap-3 p-4">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
                      <AssetIcon type={a.type} />
                    </span>
                    <span className="min-w-0 flex-1 space-y-1.5">
                      <span className="block font-medium">{a.name}</span>
                      <span className="block truncate font-mono text-xs text-subtle">{a.identifier}</span>
                      <span className="flex flex-wrap gap-1.5">
                        <MonitoringBadge status={a.monitoring_status} />
                        <CriticalityBadge level={a.criticality} />
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-between gap-4 px-4 py-3 text-sm text-muted">
              <span>
                {data.total} asset{data.total === 1 ? "" : "s"}
              </span>
              {pages > 1 && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={filters.page <= 1}
                    onClick={() => update({ page: String(filters.page - 1) })}
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <span>
                    Page {filters.page} of {pages}
                  </span>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={filters.page >= pages}
                    onClick={() => update({ page: String(filters.page + 1) })}
                    aria-label="Next page"
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              )}
            </div>
          </>
        )}
      </Card>

      {creating && (
        <AssetFormDialog
          open
          onClose={() => update({ new: null })}
          onSaved={(asset) => router.push(`/assets/${asset.id}`)}
        />
      )}
    </>
  );
}
