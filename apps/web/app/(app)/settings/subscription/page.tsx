"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Check, Download, Receipt } from "lucide-react";
import { useState } from "react";
import {
  CheckoutDialog,
  PaymentStatusBadge,
  SubscriptionBadge,
  paymentMethodLabel,
  planPrice,
} from "@/components/billing-ui";
import { Pager } from "@/components/pager";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Badge, Button, Callout, Card, CardHeader, EmptyState, Skeleton, cn } from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatCedis, formatDate } from "@/lib/format";
import type { Page, Payment, Plan, Subscription } from "@/lib/types";

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

function summary(s: Subscription) {
  const end = formatDate(s.current_period_end);
  switch (s.status) {
    case "trialing":
      return `Free trial until ${end}${s.days_left !== null ? ` (${s.days_left} day${s.days_left === 1 ? "" : "s"} left)` : ""}.`;
    case "active":
      return `Paid ${s.billing_period === "annual" ? "yearly" : "monthly"} until ${end}.`;
    case "past_due":
      return `Ended ${end}. Monitoring continues until ${formatDate(s.grace_until)} while you renew.`;
    case "expired":
      return `${s.has_paid ? "Your plan" : "Your free trial"} ended ${end}. Your data and monitoring are kept, but you can't add assets, people or devices.`;
    default:
      return "";
  }
}

const PAGE_SIZE = 10;

function PaymentHistory() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: useOrgKey("payments", { page }),
    queryFn: () => api<Page<Payment>>("/billing/payments", { query: { page, page_size: PAGE_SIZE } }),
    placeholderData: keepPreviousData,
  });
  return (
    <Card padded={false}>
      <div className="p-5 pb-1">
        <CardHeader title="Billing history" description="Receipts for every payment. Download them for your records." />
      </div>
      {isPending ? (
        <div className="p-4">
          <Skeleton className="h-24" />
        </div>
      ) : !data?.items.length ? (
        <EmptyState icon={<Receipt className="size-5" />} title="No payments yet" description="Payments and receipts appear here." />
      ) : (
        <>
          <ul className="divide-y divide-border border-t border-border">
            {data.items.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-fg">
                      {p.plan_name} · {p.billing_period === "annual" ? "12 months" : "1 month"}
                    </span>
                    <PaymentStatusBadge status={p.status} />
                  </span>
                  <span className="mt-0.5 block text-[13px] text-muted">
                    {formatDate(p.paid_at ?? p.created_at)} · {paymentMethodLabel(p)}
                    {p.receipt && ` · ${p.receipt}`}
                    {p.credit_days > 0 && ` · includes ${p.credit_days} credited days`}
                    {p.failure_reason && p.status !== "success" && ` · ${p.failure_reason}`}
                  </span>
                </span>
                <span className="font-medium tabular-nums">{formatCedis(p.amount_minor)}</span>
                {p.status === "success" && (
                  <Button
                    size="sm"
                    variant="secondary"
                    aria-label={`Download receipt ${p.receipt}`}
                    onClick={() =>
                      downloadFile(`/billing/payments/${p.id}/receipt`, `receipt-${p.receipt}.pdf`).catch((e) =>
                        toast("error", errorMessage(e)),
                      )
                    }
                  >
                    <Download className="size-4" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <Pager page={page} total={data.total} pageSize={PAGE_SIZE} noun={["payment", "payments"]} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

export default function SubscriptionPage() {
  const { can } = useSession();
  const canPay = can("billing:manage");
  const [period, setPeriod] = useState<"monthly" | "annual" | null>(null);
  const [selected, setSelected] = useState<Plan | null>(null);
  const { data } = useQuery({
    queryKey: useOrgKey("subscription"),
    queryFn: () => api<Subscription>("/billing/subscription"),
  });
  if (!data) return <Skeleton className="h-96" />;
  const billing = period ?? data.billing_period;
  const paidUp = data.status === "active";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title={`${data.plan.name} plan`} description={summary(data)} action={<SubscriptionBadge status={data.status} />} />
        <div className="grid gap-5 sm:grid-cols-3">
          <Usage label="Assets" used={data.assets_used} limit={data.plan.asset_limit} />
          <Usage label="Team members" used={data.members_used} limit={data.plan.member_limit} />
          <Usage label="Network collectors" used={data.collectors_used} limit={data.plan.collector_limit} />
        </div>
        {canPay && data.plan.monthly_price_ghs && data.status !== "trialing" && (
          <div className="mt-5">
            <Button
              variant={paidUp ? "secondary" : "primary"}
              onClick={() => {
                setPeriod(data.billing_period);
                setSelected(data.plan);
              }}
            >
              {paidUp ? "Renew early" : `Renew ${data.plan.name}`}
            </Button>
          </div>
        )}
      </Card>

      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[15px] font-semibold">Plans</h2>
          <div role="radiogroup" aria-label="Billing period" className="inline-flex rounded-lg bg-surface-2 p-1 text-sm">
            {(["monthly", "annual"] as const).map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={billing === p}
                onClick={() => setPeriod(p)}
                className={cn("rounded-md px-3 py-1.5", billing === p ? "bg-surface font-medium text-fg shadow-sm" : "text-muted hover:text-fg")}
              >
                {p === "monthly" ? "Monthly" : `Yearly · ${12 - data.annual_months_charged} months free`}
              </button>
            ))}
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
          {data.available_plans.map((p) => {
            const current = p.code === data.plan.code;
            const price = planPrice(p, billing);
            return (
              <Card key={p.code} className={cn("flex flex-col", current && "ring-2 ring-primary")}>
                <div className="flex items-center justify-between">
                  <p className="font-semibold">{p.name}</p>
                  {current && <Badge tone="primary">Current</Badge>}
                  {p.code === "business" && !current && <Badge tone="info">Most popular</Badge>}
                </div>
                <p className="mt-2 text-2xl font-semibold">
                  {price != null ? (
                    <>
                      {formatCedis(price).replace(".00", "")}
                      <span className="text-sm font-normal text-muted"> / {billing === "annual" ? "year" : "month"}</span>
                    </>
                  ) : (
                    <span className="text-lg">Custom pricing</span>
                  )}
                </p>
                {billing === "annual" && p.monthly_price_ghs && (
                  <p className="text-[13px] text-muted">Works out at {formatCedis(((p.annual_price_ghs ?? 0) * 100) / 12)} a month</p>
                )}
                <ul className="mt-4 flex-1 space-y-2 text-sm">
                  {p.features.map((f) => (
                    <li key={f} className="flex gap-2 text-muted">
                      <Check className="mt-0.5 size-4 shrink-0 text-success" /> {f}
                    </li>
                  ))}
                </ul>
                {canPay && (
                  <div className="mt-5">
                    {price == null ? (
                      <a
                        className="inline-flex w-full items-center justify-center rounded-[var(--radius-control)] border border-border px-3 py-2 text-sm font-medium hover:bg-surface-2"
                        href={`mailto:${data.contact_email}?subject=${encodeURIComponent("Enterprise plan enquiry")}`}
                      >
                        Talk to us
                      </a>
                    ) : (
                      <Button
                        className="w-full"
                        variant={current && paidUp && billing === data.billing_period ? "secondary" : "primary"}
                        onClick={() => setSelected(p)}
                      >
                        {current && billing === data.billing_period
                          ? paidUp
                            ? "Renew early"
                            : data.status === "trialing"
                              ? `Pay for ${p.name}`
                              : "Renew"
                          : `Choose ${p.name}`}
                      </Button>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
        <p className="mt-3 text-[13px] text-muted">
          Pay with Mobile Money (MTN, Telecel, AirtelTigo) or card. Plans are prepaid with no automatic charges, and
          owners get reminders 7, 3 and 1 day before a plan ends. Prices are introductory and in Ghana cedis.
        </p>
        {!canPay && (
          <div className="mt-3">
            <Callout tone="info">Only an organisation owner can change or pay for the plan.</Callout>
          </div>
        )}
      </div>

      <PaymentHistory />

      <CheckoutDialog
        key={`${selected?.code}-${billing}`}
        open={!!selected}
        onClose={() => setSelected(null)}
        plan={selected}
        period={billing}
        subscription={data}
      />
    </div>
  );
}
