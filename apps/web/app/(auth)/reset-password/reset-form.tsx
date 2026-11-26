"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthHeading, PASSWORD_HINT, PasswordInput } from "@/components/auth-forms";
import { Button, Callout, Field } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";

export function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!token) {
    return (
      <>
        <AuthHeading title="Invalid reset link" description="This link is missing its token." />
        <Link href="/forgot-password" className="text-sm font-medium text-primary-text">
          Request a new link
        </Link>
      </>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldError(undefined);
    if (password !== confirm) {
      setFieldError("The passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await api("/auth/password/reset", {
        method: "POST",
        body: { token, new_password: password },
        org: false,
        noRefresh: true,
      });
      setDone(true);
      setTimeout(() => router.replace("/login"), 2500);
    } catch (err) {
      if (err instanceof ApiError && err.details) setFieldError(err.fieldErrors().password);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <>
        <AuthHeading
          title="Password updated"
          description="You've been signed out everywhere. Sign in with your new password."
        />
        <Link href="/login" className="text-sm font-medium text-primary-text hover:underline">
          Go to sign in
        </Link>
      </>
    );
  }

  return (
    <>
      <AuthHeading title="Choose a new password" />
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && (
          <Callout tone="critical">
            {error}{" "}
            {error.includes("expired") && (
              <Link href="/forgot-password" className="underline">
                Request a new link
              </Link>
            )}
          </Callout>
        )}
        <Field label="New password" htmlFor="password" hint={PASSWORD_HINT} error={fieldError}>
          <PasswordInput
            id="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            invalid={!!fieldError}
          />
        </Field>
        <Field label="Confirm new password" htmlFor="confirm">
          <PasswordInput
            id="confirm"
            value={confirm}
            onChange={setConfirm}
            autoComplete="new-password"
          />
        </Field>
        <Button type="submit" className="w-full" loading={busy} disabled={!password || !confirm}>
          Update password
        </Button>
      </form>
    </>
  );
}
