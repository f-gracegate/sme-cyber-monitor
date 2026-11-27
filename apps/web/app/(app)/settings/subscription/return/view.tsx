"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { paymentMethodLabel } from "@/components/billing-ui";
import { useOrgKey, useSession } from "@/components/session";
import { ButtonLink, Card } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatCedis, formatDate } from "@/lib/format";
import type { Payment } from "@/lib/types";

const WAIT_MS = 60_000;

/** Where the payment provider sends people back. Confirms the payment with the server. */
export function PaymentReturn() {
  const params = useSearchParams();
  // Paystack appends ?reference=…&trxref=…; the sandbox uses ?reference=….
  const reference = params.get("reference") ?? params.get("trxref") ?? "";
  const queryClient = useQueryClient();
  const { orgId } = useSession();
  const [startedAt] = useState(() => Date.now());
  const { data, error, dataUpdatedAt } = useQuery({
    queryKey: useOrgKey("payment-verify", reference),
    queryFn: () => api<Payment>(`/billing/payments/${encodeURIComponent(reference)}/verify`, { method: "POST" }),
    enabled: !!reference,
    // Mobile Money approvals can take a little while to reach the provider: keep checking.
    refetchInterval: (q) =>
      q.state.data?.status === "pending" && q.state.dataUpdatedAt - startedAt < WAIT_MS ? 3000 : false,
  });

  useEffect(() => {
    // Refresh the plan, usage and banner, but not this confirmation (which would loop).
    if (data?.status === "success")
      queryClient.invalidateQueries({
        predicate: (q) => q.queryKey[0] === "org" && q.queryKey[1] === orgId && q.queryKey[2] !== "payment-verify",
      });
  }, [data?.status, queryClient, orgId]);

  let icon = <Loader2 className="size-6 animate-spin text-primary-text" />;
  let title = "Confirming your payment…";
  let body: React.ReactNode = "This usually takes a few seconds. If you're paying with Mobile Money, approve the prompt on your phone.";
  if (!reference) {
    icon = <CircleX className="size-6 text-critical-text" />;
    title = "No payment to confirm";
    body = "Start again from the subscription page.";
  } else if (error) {
    icon = <CircleX className="size-6 text-critical-text" />;
    title = "We couldn't confirm the payment";
    body = errorMessage(error);
  } else if (data?.status === "success") {
    icon = <CircleCheck className="size-6 text-success-text" />;
    title = "Payment received. Thank you!";
    body = (
      <>
        {formatCedis(data.amount_minor)} for the {data.plan_name} plan, paid with {paymentMethodLabel(data)}. Your plan runs until{" "}
        <strong>{formatDate(data.period_end)}</strong>. Receipt {data.receipt} is in your billing history.
      </>
    );
  } else if (data && data.status !== "pending") {
    icon = <CircleX className="size-6 text-critical-text" />;
    title = data.status === "abandoned" ? "Payment cancelled" : "Payment didn't go through";
    body = `${data.failure_reason ?? "No money was taken."} You can try again with another method.`;
  } else if (data?.status === "pending" && dataUpdatedAt - startedAt >= WAIT_MS) {
    title = "Still waiting for confirmation";
    body = "We haven't heard back from the payment provider yet. If money left your account, your plan updates automatically as soon as it's confirmed.";
  }

  return (
    <Card className="mx-auto max-w-lg text-center">
      <div className="flex flex-col items-center gap-3 py-4">
        {icon}
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted">{body}</p>
        <div className="mt-2 flex gap-2">
          <ButtonLink href="/settings/subscription">Back to subscription</ButtonLink>
          {data?.status === "success" && (
            <Link href="/getting-started" className="inline-flex items-center px-3 text-sm text-muted hover:text-fg">
              Getting started
            </Link>
          )}
        </div>
      </div>
    </Card>
  );
}
