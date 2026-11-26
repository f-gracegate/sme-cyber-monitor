"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthHeading, PASSWORD_HINT, PasswordInput } from "@/components/auth-forms";
import { Button, Callout, Field, Spinner } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function ChangePasswordPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me", { org: false }) });
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);

  const unauthenticated = me.error instanceof ApiError && me.error.status === 401;
  useEffect(() => {
    if (unauthenticated) router.replace("/login");
  }, [unauthenticated, router]);

  if (me.isPending || unauthenticated) {
    return (
      <div className="flex justify-center">
        <Spinner />
      </div>
    );
  }

  const forced = me.data?.user.must_change_password;

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
      await api("/auth/password/change", {
        method: "POST",
        org: false,
        body: { current_password: current, new_password: password },
      });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      router.replace("/overview");
    } catch (err) {
      if (err instanceof ApiError && err.details) setFieldError(err.fieldErrors().password);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-warning-soft text-warning-text">
        <LockKeyhole className="size-5" />
      </div>
      <AuthHeading
        title={forced ? "Set a new password" : "Change password"}
        description={
          forced
            ? "Your account is using a temporary password. Choose your own before continuing."
            : "You'll stay signed in here; other devices will be signed out."
        }
      />
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error && <Callout tone="critical">{error}</Callout>}
        <Field label={forced ? "Temporary password" : "Current password"} htmlFor="current">
          <PasswordInput
            id="current"
            value={current}
            onChange={setCurrent}
            autoComplete="current-password"
          />
        </Field>
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
        <Button
          type="submit"
          className="w-full"
          loading={busy}
          disabled={!current || !password || !confirm}
        >
          Save new password
        </Button>
      </form>
    </>
  );
}
