"use client";

import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthHeading, PasswordInput, safeNext } from "@/components/auth-forms";
import { Button, Callout, Field, Input } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { LoginResponse } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const next = safeNext(params.get("next"));

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function finish(res: LoginResponse) {
    if (res.status === "mfa_required" && res.mfa_token) {
      setMfaToken(res.mfa_token);
      setCode("");
      return;
    }
    if (res.me) queryClient.setQueryData(["me"], res.me);
    router.replace(res.me?.user.must_change_password ? "/change-password" : next);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = mfaToken
        ? await api<LoginResponse>("/auth/mfa/verify", {
            method: "POST",
            body: { mfa_token: mfaToken, code },
            org: false,
            noRefresh: true,
          })
        : await api<LoginResponse>("/auth/login", {
            method: "POST",
            body: { identifier, password },
            org: false,
            noRefresh: true,
          });
      await finish(res);
    } catch (err) {
      if (err instanceof ApiError && err.code === "mfa_token_expired") {
        setMfaToken(null);
      }
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (mfaToken) {
    return (
      <>
        <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-primary-soft text-primary-text">
          <ShieldCheck className="size-5" />
        </div>
        <AuthHeading
          title="Two-step verification"
          description={
            useRecovery
              ? "Enter one of the recovery codes you saved when you set up MFA."
              : "Open your authenticator app and enter the 6-digit code for this account."
          }
        />
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          {error && <Callout tone="critical">{error}</Callout>}
          <Field label={useRecovery ? "Recovery code" : "Authentication code"} htmlFor="code">
            <Input
              id="code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode={useRecovery ? "text" : "numeric"}
              autoComplete="one-time-code"
              placeholder={useRecovery ? "a1b2c3-d4e5f6" : "123456"}
              maxLength={useRecovery ? 20 : 6}
              autoFocus
              className="text-center font-mono text-lg tracking-[0.3em]"
            />
          </Field>
          <Button type="submit" className="w-full" loading={busy} disabled={code.length < 6}>
            Verify and sign in
          </Button>
          <div className="flex justify-between text-sm">
            <button
              type="button"
              className="text-primary-text hover:underline"
              onClick={() => {
                setUseRecovery((r) => !r);
                setCode("");
                setError(null);
              }}
            >
              {useRecovery ? "Use authenticator code" : "Use a recovery code"}
            </button>
            <button
              type="button"
              className="text-muted hover:text-fg"
              onClick={() => {
                setMfaToken(null);
                setPassword("");
                setError(null);
              }}
            >
              Start over
            </button>
          </div>
        </form>
      </>
    );
  }

  return (
    <>
      <AuthHeading title="Sign in" description="Welcome back. Sign in to your security workspace." />
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && <Callout tone="critical">{error}</Callout>}
        <Field label="Email or username" htmlFor="identifier">
          <Input
            id="identifier"
            name="username"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </Field>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <Link href="/forgot-password" className="text-[13px] text-primary-text hover:underline">
              Forgot password?
            </Link>
          </div>
          <PasswordInput
            id="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
          />
        </div>
        <Button
          type="submit"
          className="w-full"
          loading={busy}
          disabled={!identifier || !password}
        >
          <KeyRound className="size-4" /> Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        New to the platform?{" "}
        <Link href="/register" className="font-medium text-primary-text hover:underline">
          Create a business account
        </Link>
      </p>
    </>
  );
}
