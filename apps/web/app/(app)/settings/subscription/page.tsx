"use client";

import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useOrgKey } from "@/components/session";
import { Badge, Card, CardHeader, Skeleton, cn } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Subscription } from "@/lib/types";

function Usage({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-medium tabular-nums">
          {used} / {limit ?? "Unlimited"}
        </span>
      </div>
      <div className="h-2 rounded-full bg-surface-2">
        <div
          className={cn("h-2 rounded-full", pct >= 90 ? "bg-critical" : pct >= 70 ? "bg-warning" : "bg-primary")}
          style={{ width: `${limit ? pct : 4}%` }}
        />
      </div>
    </div>
  );
}

export default function SubscriptionPage() {
  const { data } = useQuery({
    queryKey: useOrgKey("subscription"),
    queryFn: () => api<Subscription>("/billing/subscription"),
  });
  if (!data) return <Skeleton className="h-96" />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title={`${data.plan.name} plan`}
          description={
            data.status === "trialing"
              ? `Free trial until ${formatDate(data.current_period_end)}`
              : `Renews ${formatDate(data.current_period_end)}`
          }
          action={<Badge tone={data.status === "active" || data.status === "trialing" ? "success" : "warning"}>{data.status === "trialing" ? "Trial" : data.status}</Badge>}
        />
        <div className="grid gap-5 sm:grid-cols-2">
          <Usage label="Assets" used={data.assets_used} limit={data.plan.asset_limit} />
          <Usage label="Team members" used={data.members_used} limit={data.plan.member_limit} />
        </div>
      </Card>

      <div>
        <h2 className="mb-3 text-[15px] font-semibold">Plans</h2>
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
          {data.available_plans.map((p) => {
            const current = p.code === data.plan.code;
            return (
              <Card key={p.code} className={cn("flex flex-col", current && "ring-2 ring-primary")}>
                <div className="flex items-center justify-between">
                  <p className="font-semibold">{p.name}</p>
                  {current && <Badge tone="primary">Current</Badge>}
                </div>
                <p className="mt-2 text-2xl font-semibold">
                  {p.monthly_price_ghs ? (
                    <>
                      GH₵{p.monthly_price_ghs}
                      <span className="text-sm font-normal text-muted"> / month</span>
                    </>
                  ) : (
                    <span className="text-lg">Custom pricing</span>
                  )}
                </p>
                <ul className="mt-4 flex-1 space-y-2 text-sm">
                  {p.features.map((f) => (
                    <li key={f} className="flex gap-2 text-muted">
                      <Check className="mt-0.5 size-4 shrink-0 text-success" /> {f}
                    </li>
                  ))}
                </ul>
              </Card>
            );
          })}
        </div>
        <p className="mt-3 text-[13px] text-muted">
          Online payment (Mobile Money and card) is being added. To change plan now, contact
          support. Prices are introductory and may change before commercial launch.
        </p>
      </div>
    </div>
  );
}
