"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { OrgForm, toOrgForm, toOrgPayload } from "@/components/org-form";
import { rememberOrg, useSession } from "@/components/session";
import { Button, Callout, Card } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Organisation } from "@/lib/types";

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { me } = useSession();
  const first = me.memberships.length === 0;

  const create = useMutation({
    mutationFn: (body: object) => api<Organisation>("/organisations", { method: "POST", body, org: false }),
    onSuccess: async (org) => {
      rememberOrg(org.id);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      router.replace("/getting-started");
    },
  });

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6 flex items-start gap-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-text">
          <Building2 className="size-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {first ? `Welcome, ${me.user.full_name.split(" ")[0] || "there"}` : "Add an organisation"}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {first
              ? "Tell us about your business. You'll become its owner and can invite your team next."
              : "Create a separate workspace, for example for another business you manage."}
          </p>
        </div>
      </div>
      {!me.user.email_verified_at && <VerifyNotice email={me.user.email} />}
      <Card className={me.user.email_verified_at ? undefined : "pointer-events-none opacity-50"}>
        <OrgForm
          initial={toOrgForm()}
          error={create.error}
          onSubmit={(v) => create.mutate(toOrgPayload(v))}
          footer={
            <Button type="submit" loading={create.isPending}>
              Create workspace
            </Button>
          }
        />
      </Card>
      <p className="mt-4 text-center text-[13px] text-subtle">
        New workspaces start on a 14-day Starter trial. No payment details needed.
      </p>
    </div>
  );
}

function VerifyNotice({ email }: { email: string }) {
  const resend = useMutation({
    mutationFn: () => api("/auth/email/resend", { method: "POST", org: false }),
  });
  return (
    <div className="mb-5">
      <Callout
        tone="info"
        title="Confirm your email first"
        action={
          <Button size="sm" variant="secondary" loading={resend.isPending} disabled={resend.isSuccess} onClick={() => resend.mutate()}>
            {resend.isSuccess ? "Sent" : "Resend link"}
          </Button>
        }
      >
        We sent a link to <strong>{email}</strong>. Open it to confirm the address, then come back here to create your
        workspace.
        {resend.isError && <span className="mt-1 block">{errorMessage(resend.error)}</span>}
      </Callout>
    </div>
  );
}

