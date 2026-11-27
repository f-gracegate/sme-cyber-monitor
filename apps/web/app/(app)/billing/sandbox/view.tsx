"use client";

import { useMutation } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Callout, Card } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

/**
 * Development stand-in for the payment provider's hosted checkout. The API only accepts these
 * calls when PAYMENT_PROVIDER=sandbox in a development environment.
 */
export function SandboxCheckout() {
  const router = useRouter();
  const reference = useSearchParams().get("reference") ?? "";
  const complete = useMutation({
    mutationFn: (outcome: "success" | "failed" | "abandoned") =>
      api(`/billing/sandbox/${encodeURIComponent(reference)}`, { method: "POST", body: { outcome } }),
    onSuccess: () => router.replace(`/settings/subscription/return?reference=${encodeURIComponent(reference)}`),
  });
  return (
    <Card className="mx-auto max-w-md">
      <div className="flex flex-col items-center gap-3 py-2 text-center">
        <span className="flex size-11 items-center justify-center rounded-xl bg-warning-soft text-warning-text">
          <FlaskConical className="size-5" />
        </span>
        <h1 className="text-lg font-semibold">Test checkout</h1>
        <p className="text-sm text-muted">
          This page stands in for the Mobile Money / card checkout during development. No money moves.
        </p>
        <p className="font-mono text-xs text-subtle">{reference}</p>
        {complete.isError && <Callout tone="critical">{errorMessage(complete.error)}</Callout>}
        <div className="mt-2 grid w-full gap-2">
          <Button loading={complete.isPending && complete.variables === "success"} onClick={() => complete.mutate("success")}>
            Approve payment
          </Button>
          <Button variant="secondary" loading={complete.isPending && complete.variables === "failed"} onClick={() => complete.mutate("failed")}>
            Decline
          </Button>
          <Button variant="ghost" loading={complete.isPending && complete.variables === "abandoned"} onClick={() => complete.mutate("abandoned")}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}
