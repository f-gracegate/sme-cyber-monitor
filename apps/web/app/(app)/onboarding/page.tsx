"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { OrgForm, toOrgForm, toOrgPayload } from "@/components/org-form";
import { rememberOrg, useSession } from "@/components/session";
import { Button, Card } from "@/components/ui";
import { api } from "@/lib/api";
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
      router.replace("/overview");
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
      <Card>
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
