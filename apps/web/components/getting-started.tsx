"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, Smartphone } from "lucide-react";
import Link from "next/link";
import { useOrgKey, useSession } from "@/components/session";
import { Badge, Button, Card, CardHeader, cn } from "@/components/ui";
import { api } from "@/lib/api";
import type { Onboarding, OnboardingStep } from "@/lib/types";

export function useOnboarding() {
  const { orgId, membership } = useSession();
  const { data } = useQuery({
    queryKey: useOrgKey("onboarding"),
    queryFn: () => api<Onboarding>("/onboarding"),
    enabled: !!orgId && !!membership,
    staleTime: 60_000,
  });
  return data;
}

export function useDismissOnboarding() {
  const queryClient = useQueryClient();
  const key = useOrgKey("onboarding");
  return useMutation({
    mutationFn: (dismissed: boolean) =>
      api<Onboarding>("/onboarding/dismissed", { method: "PUT", body: { dismissed } }),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });
}

function Progress({ data }: { data: Onboarding }) {
  const pct = data.required ? Math.round((data.required_done / data.required) * 100) : 100;
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Setup progress">
        <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${Math.max(pct, 4)}%` }} />
      </div>
      <span className="text-sm font-medium tabular-nums text-muted">
        {data.required_done} of {data.required}
      </span>
    </div>
  );
}

export function StepRow({ step, index, compact }: { step: OnboardingStep; index: number; compact?: boolean }) {
  const marker = (
    <span
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
        step.done ? "bg-success text-white" : "border border-border bg-surface text-muted",
      )}
      aria-hidden
    >
      {step.done ? <Check className="size-4" /> : index + 1}
    </span>
  );
  return (
    <li className={cn("flex items-start gap-3", compact ? "py-2.5" : "px-5 py-4")}>
      {marker}
      <div className="min-w-0 flex-1">
        <p className={cn("flex flex-wrap items-center gap-2 font-medium", step.done ? "text-muted line-through decoration-subtle" : "text-fg")}>
          {step.title}
          {step.optional && !step.done && <Badge>Optional</Badge>}
        </p>
        {!compact && <p className="mt-0.5 text-sm text-muted">{step.description}</p>}
        {!compact && step.id === "mobile" && !step.done && (
          <p className="mt-2 inline-flex items-center gap-1.5 text-[13px] text-muted">
            <Smartphone className="size-3.5" /> Open the SME Cybersecurity Monitoring app on your Android phone or iPhone, sign in with this account and tap Allow.
          </p>
        )}
      </div>
      {!step.done && step.href && (
        <Link
          href={step.href}
          className={cn(
            "inline-flex shrink-0 items-center gap-1 text-sm font-medium text-primary-text hover:underline",
            compact && "self-center",
          )}
        >
          {compact ? <ChevronRight className="size-4" aria-label={step.action_label ?? "Open"} /> : step.action_label}
        </Link>
      )}
    </li>
  );
}

/** Compact checklist for the overview while setup is unfinished. */
export function GettingStartedCard() {
  const data = useOnboarding();
  const { can } = useSession();
  const dismiss = useDismissOnboarding();
  if (!data || data.dismissed || data.complete) return null;
  const next = data.steps.filter((s) => !s.done && !s.optional).slice(0, 3);
  return (
    <Card>
      <CardHeader
        title="Finish setting up"
        description="A few steps to get your business fully monitored."
        action={
          <div className="flex items-center gap-2">
            {can("org:update") && (
              <Button size="sm" variant="ghost" loading={dismiss.isPending} onClick={() => dismiss.mutate(true)}>
                Hide
              </Button>
            )}
            <Link href="/getting-started" className="text-sm font-medium text-primary-text hover:underline">
              See all steps
            </Link>
          </div>
        }
      />
      <Progress data={data} />
      <ul className="mt-2 divide-y divide-border">
        {next.map((s) => (
          <StepRow key={s.id} step={s} index={data.steps.indexOf(s)} compact />
        ))}
      </ul>
    </Card>
  );
}

export function GettingStartedProgress({ data }: { data: Onboarding }) {
  return <Progress data={data} />;
}
