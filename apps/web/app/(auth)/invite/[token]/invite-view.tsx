"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AuthHeading } from "@/components/auth-forms";
import { rememberOrg } from "@/components/session";
import { Badge, Button, ButtonLink, Callout, Skeleton } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";

type Preview = {
  organisation_name: string;
  email: string;
  role: string;
  role_label: string;
  status: "pending" | "expired" | "accepted" | "revoked";
  account_exists: boolean;
};

export function InviteView() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const preview = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api<Preview>(`/auth/invitations/${token}`, { org: false, noRefresh: true }),
  });
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/auth/me", { org: false }),
    retry: false,
  });
  const accept = useMutation({
    mutationFn: () =>
      api<Me>("/auth/invitations/accept", { method: "POST", body: { token }, org: false }),
    onSuccess: (data) => {
      queryClient.setQueryData(["me"], data);
      const joined = data.memberships.find(
        (m) => m.organisation_name === preview.data?.organisation_name,
      );
      if (joined) rememberOrg(joined.organisation_id);
      router.replace("/overview");
    },
  });

  if (preview.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }
  if (preview.isError) {
    return (
      <>
        <AuthHeading title="Invitation not found" description={errorMessage(preview.error)} />
        <Link href="/login" className="text-sm font-medium text-primary-text">
          Go to sign in
        </Link>
      </>
    );
  }

  const inv = preview.data;
  if (inv.status !== "pending") {
    const reason = {
      expired: "This invitation has expired. Ask your administrator to send a new one.",
      accepted: "This invitation has already been used.",
      revoked: "This invitation was cancelled by an administrator.",
    }[inv.status];
    return (
      <>
        <AuthHeading title="Invitation unavailable" description={reason} />
        <Link href="/login" className="text-sm font-medium text-primary-text">
          Go to sign in
        </Link>
      </>
    );
  }

  const signedInAs = me.data?.user.email;
  const sameUser = signedInAs?.toLowerCase() === inv.email.toLowerCase();
  const next = encodeURIComponent(`/invite/${token}`);

  return (
    <>
      <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-primary-soft text-primary-text">
        <Building2 className="size-5" />
      </div>
      <AuthHeading
        title={`Join ${inv.organisation_name}`}
        description={
          <>
            You&apos;ve been invited as <Badge tone="primary">{inv.role_label}</Badge> using{" "}
            <strong className="text-fg">{inv.email}</strong>.
          </>
        }
      />
      {accept.isError && (
        <div className="mb-4">
          <Callout tone="critical">{errorMessage(accept.error)}</Callout>
        </div>
      )}
      {signedInAs && sameUser ? (
        <Button className="w-full" loading={accept.isPending} onClick={() => accept.mutate()}>
          Accept invitation
        </Button>
      ) : signedInAs ? (
        <Callout tone="warning" title={`You're signed in as ${signedInAs}`}>
          This invitation is for {inv.email}. Sign out, then open the link again.
        </Callout>
      ) : inv.account_exists ? (
        <ButtonLink href={`/login?next=${next}`} className="w-full">
          Sign in to accept
        </ButtonLink>
      ) : (
        <ButtonLink
          href={`/register?invite=${token}&email=${encodeURIComponent(inv.email)}`}
          className="w-full"
        >
          Create account and join
        </ButtonLink>
      )}
      {me.error instanceof ApiError && me.error.status !== 401 && (
        <p className="mt-3 text-sm text-critical-text">{errorMessage(me.error)}</p>
      )}
    </>
  );
}
