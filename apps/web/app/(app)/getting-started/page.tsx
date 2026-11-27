"use client";

import { PartyPopper } from "lucide-react";
import { GettingStartedProgress, StepRow, useDismissOnboarding, useOnboarding } from "@/components/getting-started";
import { useSession } from "@/components/session";
import { Button, ButtonLink, Callout, Card, PageHeader, Skeleton } from "@/components/ui";

export default function GettingStartedPage() {
  const data = useOnboarding();
  const { can, membership } = useSession();
  const dismiss = useDismissOnboarding();
  return (
    <>
      <PageHeader
        title="Getting started"
        description={`Set up ${membership?.organisation_name ?? "your business"} for monitoring. Most businesses finish in about 15 minutes.`}
        actions={
          data &&
          can("org:update") &&
          (data.dismissed ? (
            <Button variant="secondary" loading={dismiss.isPending} onClick={() => dismiss.mutate(false)}>
              Show on overview
            </Button>
          ) : (
            <Button variant="secondary" loading={dismiss.isPending} onClick={() => dismiss.mutate(true)}>
              Hide checklist
            </Button>
          ))
        }
      />
      {!data ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="mx-auto max-w-3xl space-y-5">
          {data.complete && (
            <Callout tone="success" icon={<PartyPopper className="size-4" />} title="You're set up">
              Your business is being monitored. We&apos;ll alert you when something needs attention.{" "}
              <ButtonLink href="/overview" size="sm" variant="secondary">
                Go to overview
              </ButtonLink>
            </Callout>
          )}
          <Card padded={false}>
            <div className="p-5">
              <GettingStartedProgress data={data} />
            </div>
            <ol className="divide-y divide-border border-t border-border">
              {data.steps.map((s, i) => (
                <StepRow key={s.id} step={s} index={i} />
              ))}
            </ol>
          </Card>
          <p className="text-center text-[13px] text-muted">
            Need help? Our team can set things up with you, on site or remotely.
          </p>
        </div>
      )}
    </>
  );
}
