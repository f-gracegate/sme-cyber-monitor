"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { FeedbackInbox, PilotMetrics } from "@/components/platform-pilot";
import { useSession } from "@/components/session";
import { Badge, Callout, Card, EmptyState, PageHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { INDUSTRIES } from "@/lib/labels";
import type { PlatformOrganisation } from "@/lib/types";

export default function PlatformPage() {
  const { me } = useSession();
  const { data, isPending } = useQuery({
    queryKey: ["platform", "organisations"],
    queryFn: () => api<PlatformOrganisation[]>("/platform/organisations", { org: false }),
    enabled: me.user.is_platform_admin,
  });

  if (!me.user.is_platform_admin) {
    return <EmptyState icon={<ShieldAlert className="size-5" />} title="Platform administrators only" />;
  }

  return (
    <>
      <PageHeader
        title="Customer organisations"
        description="Platform operations view. Shows counts only. Customer data stays inside each organisation and needs an invitation to view."
      />
      <div className="mb-4">
        <Callout tone="info">
          Platform administrators don&apos;t automatically see customer assets or audit logs. This
          keeps least-privilege access between your team and your customers.
        </Callout>
      </div>
      <Card padded={false}>
        {isPending ? (
          <div className="p-5">
            <Skeleton className="h-40" />
          </div>
        ) : !data?.length ? (
          <EmptyState title="No organisations yet" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Organisation</Th>
                <Th>Industry</Th>
                <Th>Plan</Th>
                <Th>Members</Th>
                <Th>Assets</Th>
                <Th>Status</Th>
                <Th>Created</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((o) => (
                <tr key={o.id}>
                  <Td className="font-medium">{o.name}</Td>
                  <Td className="text-muted">
                    {INDUSTRIES.find((i) => i.value === o.industry)?.label ?? "—"}
                  </Td>
                  <Td className="capitalize">{o.plan_code ?? "—"}</Td>
                  <Td className="tabular-nums">{o.members}</Td>
                  <Td className="tabular-nums">{o.assets}</Td>
                  <Td>
                    <Badge tone={o.status === "active" ? "success" : "warning"}>{o.status}</Badge>
                  </Td>
                  <Td className="text-muted">{formatDate(o.created_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <div className="mt-6 space-y-6">
        <PilotMetrics />
        <FeedbackInbox />
      </div>
    </>
  );
}
