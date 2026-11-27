"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CreditCard, Smartphone } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { useOrgKey, useSession } from "@/components/session";
import { Badge, Button, Callout, cn } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatCedis, formatDate } from "@/lib/format";
import type { CheckoutResult, Payment, PaymentChannel, Plan, Subscription } from "@/lib/types";

type Tone = "neutral" | "info" | "primary" | "success" | "warning" | "high" | "critical";

export const SUBSCRIPTION_STATUS: Record<string, { label: string; tone: Tone }> = {
  trialing: { label: "Free trial", tone: "info" },
  active: { label: "Active", tone: "success" },
  past_due: { label: "Payment due", tone: "warning" },
  expired: { label: "Ended", tone: "critical" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const PAYMENT_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending: { label: "Awaiting payment", tone: "neutral" },
  success: { label: "Paid", tone: "success" },
  failed: { label: "Failed", tone: "critical" },
  abandoned: { label: "Cancelled", tone: "neutral" },
};

export function SubscriptionBadge({ status }: { status: string }) {
  const meta = SUBSCRIPTION_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function PaymentStatusBadge({ status }: { status: string }) {
  const meta = PAYMENT_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function paymentMethodLabel(p: Payment) {
  const m = p.payment_method;
  if (p.channel === "card") return m.last4 ? `${(m.brand ?? "Card").replace(/^\w/, (c) => c.toUpperCase())} ···· ${m.last4}` : "Card";
  return [m.network, m.phone].filter(Boolean).join(" ") || "Mobile Money";
}

export function planPrice(plan: Plan, period: "monthly" | "annual") {
  const ghs = period === "annual" ? plan.annual_price_ghs : plan.monthly_price_ghs;
  return ghs == null ? null : ghs * 100;
}

const CHANNELS: { value: PaymentChannel; label: string; hint: string; icon: typeof Smartphone }[] = [
  { value: "mobile_money", label: "Mobile Money", hint: "MTN MoMo, Telecel Cash or AirtelTigo Money", icon: Smartphone },
  { value: "card", label: "Card", hint: "Visa, Mastercard or Verve", icon: CreditCard },
];

/** Confirm the plan, pick Mobile Money or card, then go to the provider's secure checkout. */
export function CheckoutDialog({
  open,
  onClose,
  plan,
  period,
  subscription,
}: {
  open: boolean;
  onClose: () => void;
  plan: Plan | null;
  period: "monthly" | "annual";
  subscription: Subscription;
}) {
  const [channel, setChannel] = useState<PaymentChannel>("mobile_money");
  const start = useMutation({
    mutationFn: () =>
      api<CheckoutResult>("/billing/checkout", {
        method: "POST",
        body: { plan_code: plan?.code, billing_period: period, channel },
      }),
    onSuccess: (r) => {
      window.location.assign(r.authorization_url);
    },
  });
  if (!plan) return null;
  const amount = planPrice(plan, period) ?? 0;
  const paidUp = subscription.status === "active" || subscription.status === "past_due";
  const samePlan = plan.code === subscription.plan.code && period === subscription.billing_period;
  const renewing = samePlan && paidUp;
  const changing = !samePlan && paidUp;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={renewing ? `Renew ${plan.name}` : samePlan || !paidUp ? `Pay for ${plan.name}` : `Switch to ${plan.name}`}
      description="You'll finish payment on our payment partner's secure page. We never see your card or wallet PIN."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={start.isPending || start.isSuccess} onClick={() => start.mutate()}>
            Pay {formatCedis(amount)}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {start.isError && <Callout tone="critical">{errorMessage(start.error)}</Callout>}
        <div className="rounded-[var(--radius-control)] border border-border bg-surface-2 p-3.5 text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-medium text-fg">
              {plan.name} · {period === "annual" ? "12 months" : "1 month"}
            </span>
            <span className="text-lg font-semibold tabular-nums">{formatCedis(amount)}</span>
          </div>
          <p className="mt-1 text-[13px] text-muted">
            {renewing && subscription.status === "active"
              ? `Adds ${period === "annual" ? "a year" : "a month"} after your current period ends on ${formatDate(subscription.current_period_end)}.`
              : changing
                ? "Starts today. Unused time on your current plan is added as extra days."
                : "Starts as soon as payment is confirmed."}{" "}
            Prepaid, no automatic charges. We&apos;ll remind you before it ends.
          </p>
        </div>
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-fg">Pay with</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {CHANNELS.map((c) => (
              <label
                key={c.value}
                className={cn(
                  "flex cursor-pointer gap-3 rounded-[var(--radius-control)] border p-3 text-sm transition-colors",
                  channel === c.value ? "border-primary bg-primary-soft/40 ring-1 ring-primary" : "border-border hover:bg-surface-2",
                )}
              >
                <input
                  type="radio"
                  name="channel"
                  value={c.value}
                  checked={channel === c.value}
                  onChange={() => setChannel(c.value)}
                  className="sr-only"
                />
                <c.icon className="mt-0.5 size-4 shrink-0 text-primary-text" />
                <span>
                  <span className="block font-medium text-fg">{c.label}</span>
                  <span className="block text-[13px] text-muted">{c.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {subscription.payment_provider === "sandbox" && (
          <Callout tone="warning">Test mode: no real money moves. You&apos;ll see a simulated checkout.</Callout>
        )}
      </div>
    </Dialog>
  );
}

/** App-wide reminder when the trial is ending or the subscription needs paying. */
export function SubscriptionBanner() {
  const { can, orgId } = useSession();
  const { data } = useQuery({
    queryKey: useOrgKey("subscription"),
    queryFn: () => api<Subscription>("/billing/subscription"),
    enabled: !!orgId && can("billing:read"),
    staleTime: 5 * 60_000,
  });
  if (!data) return null;
  const pay = can("billing:manage");
  const cta = (
    <Link href="/settings/subscription" className="font-medium underline underline-offset-2">
      {pay ? "Choose a plan" : "View subscription"}
    </Link>
  );
  let tone: Tone | null = null;
  let text = "";
  if (data.status === "expired") {
    tone = "critical";
    text = `${data.has_paid ? "Your subscription" : "Your free trial"} has ended. Monitoring continues, but you can't add assets, people or devices.`;
  } else if (data.status === "past_due") {
    tone = "warning";
    text = `Payment is due. Monitoring continues until ${formatDate(data.grace_until)}.`;
  } else if (data.status === "trialing" && data.days_left !== null && data.days_left <= 3) {
    tone = "info";
    text = data.days_left <= 0 ? "Your free trial ends today." : `Your free trial ends in ${data.days_left} day${data.days_left === 1 ? "" : "s"}.`;
  }
  if (!tone) return null;
  return (
    <div className="mb-5">
      <Callout tone={tone}>
        {text} {cta}
      </Callout>
    </div>
  );
}
