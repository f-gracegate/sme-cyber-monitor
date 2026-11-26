"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck, ShieldOff, Smartphone, TriangleAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { CopyField } from "@/components/copy-field";
import { Dialog } from "@/components/dialog";
import { useToast } from "@/components/providers";
import { useSession } from "@/components/session";
import {
  Badge,
  Button,
  ButtonLink,
  Callout,
  Card,
  CardHeader,
  Field,
  Input,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Organisation } from "@/lib/types";

function MfaSetup({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [secret, setSecret] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);

  const setup = useMutation({
    mutationFn: () =>
      api<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup", { method: "POST", org: false }),
    onSuccess: setSecret,
  });
  const enable = useMutation({
    mutationFn: () =>
      api<{ recovery_codes: string[] }>("/auth/mfa/enable", {
        method: "POST",
        org: false,
        body: { code },
      }),
    onSuccess: (res) => setCodes(res.recovery_codes),
  });

  if (codes) {
    return (
      <div className="space-y-4">
        <Callout tone="success" icon={<ShieldCheck className="size-4" />} title="Multi-factor authentication is on">
          Save these recovery codes somewhere safe, like a password manager. Each one works once
          if you lose your phone. They won&apos;t be shown again.
        </Callout>
        <ul className="grid grid-cols-2 gap-2 rounded-[var(--radius-control)] border border-border bg-surface-2 p-4 font-mono text-sm sm:grid-cols-5">
          {codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => navigator.clipboard?.writeText(codes.join("\n"))}
          >
            Copy codes
          </Button>
          <Button
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["me"] });
              onDone();
            }}
          >
            I&apos;ve saved them
          </Button>
        </div>
      </div>
    );
  }

  if (!secret) {
    return (
      <div className="space-y-3">
        {setup.isError && <Callout tone="critical">{errorMessage(setup.error)}</Callout>}
        <p className="text-sm text-muted">
          You&apos;ll need an authenticator app such as Google Authenticator, Microsoft
          Authenticator or 1Password on your phone.
        </p>
        <Button loading={setup.isPending} onClick={() => setup.mutate()}>
          <Smartphone className="size-4" /> Set up authenticator app
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-6 md:grid-cols-[auto_minmax(0,1fr)]">
      <div className="flex flex-col items-center gap-2">
        <div className="rounded-xl bg-white p-3 ring-1 ring-border">
          <QRCodeSVG value={secret.otpauth_uri} size={168} />
        </div>
        <p className="text-xs text-subtle">Scan with your authenticator app</p>
      </div>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          enable.mutate();
        }}
      >
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
          <li>Open your authenticator app and add a new account.</li>
          <li>Scan the QR code, or enter the key below by hand.</li>
          <li>Type the 6-digit code the app shows.</li>
        </ol>
        <CopyField label="Setup key" value={secret.secret} />
        {enable.isError && <Callout tone="critical">{errorMessage(enable.error)}</Callout>}
        <Field label="6-digit code" htmlFor="mfa-code">
          <Input
            id="mfa-code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            className="max-w-40 text-center font-mono text-lg tracking-[0.3em]"
            autoFocus
          />
        </Field>
        <Button type="submit" loading={enable.isPending} disabled={code.length !== 6}>
          Verify and turn on
        </Button>
      </form>
    </div>
  );
}

function DisableMfa() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const disable = useMutation({
    mutationFn: () =>
      api("/auth/mfa/disable", { method: "POST", org: false, body: { password, code } }),
    onSuccess: () => {
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["me"] });
      toast("success", "Multi-factor authentication turned off.");
    },
  });
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <ShieldOff className="size-4" /> Turn off
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Turn off multi-factor authentication?"
        description="Your account will be protected by your password only. Organisations that require MFA will block you until you turn it back on."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={disable.isPending}
              disabled={!password || code.length < 6}
              onClick={() => disable.mutate()}
            >
              Turn off MFA
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {disable.isError && <Callout tone="critical">{errorMessage(disable.error)}</Callout>}
          <Field label="Password" htmlFor="dis-pass">
            <Input
              id="dis-pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </Field>
          <Field label="Authenticator or recovery code" htmlFor="dis-code">
            <Input id="dis-code" value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
        </div>
      </Dialog>
    </>
  );
}

function OrgMfaPolicy() {
  const { orgId, membership, can, me } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (require_mfa: boolean) =>
      api<Organisation>(`/organisations/${orgId}`, { method: "PATCH", body: { require_mfa } }),
    onSuccess: (org) => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId] });
      toast(
        "success",
        org.require_mfa ? "MFA is now required for everyone." : "MFA is no longer required.",
      );
    },
    onError: (err) => toast("error", errorMessage(err)),
  });
  if (!membership || !can("org:update")) return null;
  const on = membership.require_mfa;
  return (
    <Card>
      <CardHeader
        title="Organisation policy"
        description={`Applies to every member of ${membership.organisation_name}.`}
      />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex-1">
          <p className="flex items-center gap-2 font-medium">
            Require multi-factor authentication
            <Badge tone={on ? "success" : "neutral"}>{on ? "Required" : "Optional"}</Badge>
          </p>
          <p className="mt-0.5 text-sm text-muted">
            Members without MFA will be asked to set it up before they can see anything else.
          </p>
          {!on && !me.user.mfa_enabled && (
            <p className="mt-1 text-[13px] text-warning-text">
              Turn on MFA for your own account first.
            </p>
          )}
        </div>
        <Button
          variant={on ? "secondary" : "primary"}
          loading={toggle.isPending}
          disabled={!on && !me.user.mfa_enabled}
          onClick={() => toggle.mutate(!on)}
        >
          {on ? "Make optional" : "Require MFA"}
        </Button>
      </div>
    </Card>
  );
}

export function SecuritySettings() {
  const { me, membership } = useSession();
  const required = useSearchParams().get("required") === "1";
  const [settingUp, setSettingUp] = useState(false);
  const enabled = me.user.mfa_enabled;

  return (
    <div className="space-y-6">
      {required && !enabled && (
        <Callout tone="warning" icon={<TriangleAlert className="size-4" />} title="Multi-factor authentication required">
          {membership?.organisation_name ?? "Your organisation"} requires every member to use MFA.
          Set it up below to continue.
        </Callout>
      )}

      <Card>
        <CardHeader
          title="Multi-factor authentication"
          description="A code from your phone is needed at sign-in, so a stolen password alone isn't enough."
          action={<Badge tone={enabled ? "success" : "critical"}>{enabled ? "On" : "Off"}</Badge>}
        />
        {enabled && !settingUp ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <p className="flex flex-1 items-center gap-2 text-sm text-muted">
              <ShieldCheck className="size-4 text-success" /> Your account is protected with an
              authenticator app.
            </p>
            <DisableMfa />
          </div>
        ) : (
          <MfaSetup onDone={() => setSettingUp(false)} />
        )}
      </Card>

      <Card>
        <CardHeader title="Password" description="Changing your password signs you out on other devices." />
        <ButtonLink href="/change-password" variant="secondary">
          <KeyRound className="size-4" /> Change password
        </ButtonLink>
      </Card>

      <OrgMfaPolicy />
    </div>
  );
}
