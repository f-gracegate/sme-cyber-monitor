"use client";

import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthHeading } from "@/components/auth-forms";
import { Button, Callout, Field, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/auth/password/forgot", {
        method: "POST",
        body: { email },
        org: false,
        noRefresh: true,
      });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <>
        <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-success-soft text-success-text">
          <MailCheck className="size-5" />
        </div>
        <AuthHeading
          title="Check your email"
          description={
            <>
              If an account exists for <strong className="text-fg">{email}</strong>, we&apos;ve
              sent a link to reset your password. It expires in 30 minutes.
            </>
          }
        />
        <Link href="/login" className="text-sm font-medium text-primary-text hover:underline">
          Back to sign in
        </Link>
      </>
    );
  }

  return (
    <>
      <AuthHeading
        title="Reset your password"
        description="Enter the email you use to sign in and we'll send you a reset link."
      />
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && <Callout tone="critical">{error}</Callout>}
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            autoFocus
            required
          />
        </Field>
        <Button type="submit" className="w-full" loading={busy} disabled={!email}>
          Send reset link
        </Button>
      </form>
      <p className="mt-6 text-center text-sm">
        <Link href="/login" className="text-muted hover:text-fg">
          Back to sign in
        </Link>
      </p>
    </>
  );
}
