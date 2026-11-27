"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { AuthHeading } from "@/components/auth-forms";
import { Callout, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export function VerifyEmail() {
  const token = useSearchParams().get("token") ?? "";
  const queryClient = useQueryClient();
  const { isSuccess, error, isPending } = useQuery({
    queryKey: ["verify-email", token],
    queryFn: () => api("/auth/email/verify", { method: "POST", body: { token }, org: false }),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (isSuccess) queryClient.invalidateQueries({ queryKey: ["me"] });
  }, [isSuccess, queryClient]);

  if (!token) {
    return <AuthHeading title="Invalid link" description="This link is missing its token." />;
  }
  if (isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner /> Confirming your email…
      </div>
    );
  }
  if (error) {
    return (
      <>
        <AuthHeading title="We couldn't confirm your email" />
        <Callout tone="critical">{errorMessage(error)}</Callout>
        <p className="mt-4 text-sm text-muted">Sign in and ask for a new link from the setup page.</p>
      </>
    );
  }
  return (
    <>
      <AuthHeading title="Email confirmed" description="Thanks. You can now set up your business workspace." />
      <Link href="/onboarding" className="text-sm font-medium text-primary-text">
        Continue
      </Link>
    </>
  );
}
