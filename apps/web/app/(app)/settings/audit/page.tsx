"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useOrgKey } from "@/components/session";
import { Button, Card, CardHeader, EmptyState, Input, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { auditLabel } from "@/lib/labels";
import type { AuditEntry, Page } from "@/lib/types";

const PAGE_SIZE = 50;
const RESOURCE_TYPES = [
  { value: "", label: "Everything" },
  { value: "asset", label: "Assets" },
  { value: "membership", label: "Members" },
  { value: "invitation", label: "Invitations" },
  { value: "organisation", label: "Organisation" },
  { value: "department", label: "Departments" },
];

function describe(e: AuditEntry): string {
  const d = e.details ?? {};
  if (typeof d.name === "string") return d.name;
  if (typeof d.email === "string") return d.email;
  if (Array.isArray(d.fields)) return `Fields: ${(d.fields as string[]).join(", ")}`;
  if (d.role && typeof d.role === "object") {
    const r = d.role as { from: string; to: string };
    return `Role ${r.from} → ${r.to}`;
  }
  if (typeof d.method === "string") return `Method: ${d.method}`;
  return "";
}

export default function AuditPage() {
  const [resourceType, setResourceType] = useState("");
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: useOrgKey("audit", { resourceType, actor, page }),
    queryFn: () =>
      api<Page<AuditEntry>>("/audit-logs", {
        query: { resource_type: resourceType, actor, page, page_size: PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
  });
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Card padded={false}>
      <div className="p-5 pb-0">
        <CardHeader
          title="Audit history"
          description="Every security-relevant action in this organisation. Entries can't be edited or deleted."
        />
        <div className="mb-4 flex flex-col gap-3 sm:flex-row">
          <Select
            aria-label="Filter by area"
            value={resourceType}
            onChange={(e) => {
              setResourceType(e.target.value);
              setPage(1);
            }}
            className="sm:w-48"
          >
            {RESOURCE_TYPES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
          <Input
            aria-label="Filter by person"
            placeholder="Filter by person (email)"
            value={actor}
            onChange={(e) => {
              setActor(e.target.value);
              setPage(1);
            }}
            className="sm:max-w-xs"
          />
        </div>
      </div>
      {isPending ? (
        <div className="p-5">
          <Skeleton className="h-48" />
        </div>
      ) : !data?.items.length ? (
        <EmptyState title="No matching entries" />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Action</Th>
                <Th>Who</Th>
                <Th>Details</Th>
                <Th>IP address</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap text-muted">{formatDateTime(e.created_at)}</Td>
                  <Td className="font-medium">{auditLabel(e.action)}</Td>
                  <Td className="text-muted">{e.actor_label ?? "System"}</Td>
                  <Td className="max-w-xs truncate text-muted">{describe(e)}</Td>
                  <Td className="font-mono text-xs text-subtle">{e.ip_address ?? "—"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="flex items-center justify-between px-5 py-3 text-sm text-muted">
            <span>{data.total} entries</span>
            {pages > 1 && (
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">
                  <ChevronLeft className="size-4" />
                </Button>
                <span>
                  Page {page} of {pages}
                </span>
                <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page">
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
