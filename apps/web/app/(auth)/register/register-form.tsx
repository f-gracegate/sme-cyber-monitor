"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthHeading, PASSWORD_HINT, PasswordInput } from "@/components/auth-forms";
import { Button, Callout, Field, Input } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";

export function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const invitation = params.get("invite");

  const [form, setForm] = useState({
    full_name: "",
    email: params.get("email") ?? "",
    password: "",
    accept: false,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof form) => (value: string | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setErrors({});
    if (!form.accept) {
      setErrors({ accept: "You need to accept the terms and privacy notice." });
      return;
    }
    setBusy(true);
    try {
      const me = await api<Me>("/auth/register", {
        method: "POST",
        org: false,
        noRefresh: true,
        body: {
          full_name: form.full_name,
          email: form.email,
          password: form.password,
          invitation_token: invitation ?? undefined,
        },
      });
      queryClient.setQueryData(["me"], me);
      router.replace(me.memberships.length ? "/overview" : "/onboarding");
    } catch (err) {
      if (err instanceof ApiError && err.details) setErrors(err.fieldErrors());
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AuthHeading
        title={invitation ? "Create your account" : "Create a business account"}
        description={
          invitation
            ? "Set up your login to join your team's security workspace."
            : "Start monitoring your business's security in a few minutes."
        }
      />
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && <Callout tone="critical">{error}</Callout>}
        <Field label="Full name" htmlFor="full_name" error={errors.full_name}>
          <Input
            id="full_name"
            value={form.full_name}
            onChange={(e) => set("full_name")(e.target.value)}
            autoComplete="name"
            invalid={!!errors.full_name}
            required
          />
        </Field>
        <Field label="Work email" htmlFor="email" error={errors.email}>
          <Input
            id="email"
            type="email"
            value={form.email}
            onChange={(e) => set("email")(e.target.value)}
            autoComplete="email"
            invalid={!!errors.email}
            readOnly={Boolean(invitation && params.get("email"))}
            required
          />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password} hint={PASSWORD_HINT}>
          <PasswordInput
            id="password"
            value={form.password}
            onChange={set("password")}
            autoComplete="new-password"
            invalid={!!errors.password}
          />
        </Field>
        <div>
          <label className="flex items-start gap-2.5 text-sm text-muted">
            <input
              type="checkbox"
              checked={form.accept}
              onChange={(e) => set("accept")(e.target.checked)}
              className="mt-0.5 size-4 rounded border-border-strong accent-[var(--primary)]"
            />
            <span>
              I agree to the{" "}
              <Link href="/legal/terms" className="text-primary-text hover:underline">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/legal/privacy" className="text-primary-text hover:underline">
                Privacy Notice
              </Link>
              .
            </span>
          </label>
          {errors.accept && <p className="mt-1.5 text-[13px] text-critical-text">{errors.accept}</p>}
        </div>
        <Button type="submit" className="w-full" loading={busy}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary-text hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
