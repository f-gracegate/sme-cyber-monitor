"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOrgKey, useSession } from "@/components/session";
import { useToast } from "@/components/providers";
import { Smartphone, Trash2 } from "lucide-react";
import { Badge, Button, Callout, Card, CardHeader, Field, Select, Skeleton } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { NotificationPreferences, PushDevice } from "@/lib/types";
import { useState } from "react";

const LEVELS = [
  { value: "critical", label: "Critical only" },
  { value: "high", label: "High and critical" },
  { value: "medium", label: "Medium and above" },
  { value: "low", label: "Everything except informational" },
  { value: "off", label: "Off" },
];

function PreferencesForm({ initial }: { initial: NotificationPreferences }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("notification-preferences");
  const [prefs, setPrefs] = useState(initial);
  const save = useMutation({
    mutationFn: () =>
      api<NotificationPreferences>("/notifications/preferences", { method: "PUT", body: prefs }),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      toast("success", "Notification settings saved.");
    },
    onError: (err) => toast("error", errorMessage(err)),
  });
  return (
    <form
      className="grid gap-5 sm:grid-cols-2 2xl:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Email me about" htmlFor="email-level" hint="Sent to your sign-in email address.">
        <Select
          id="email-level"
          value={prefs.email_min_severity}
          onChange={(e) => setPrefs((p) => ({ ...p, email_min_severity: e.target.value }))}
        >
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Push to my phone" htmlFor="push-level" hint="Through the mobile app, on every phone you sign in to.">
        <Select
          id="push-level"
          value={prefs.push_min_severity}
          onChange={(e) => setPrefs((p) => ({ ...p, push_min_severity: e.target.value }))}
        >
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Show in the app" htmlFor="app-level" hint="The bell in the top bar.">
        <Select
          id="app-level"
          value={prefs.in_app_min_severity}
          onChange={(e) => setPrefs((p) => ({ ...p, in_app_min_severity: e.target.value }))}
        >
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </Field>
      <div className="col-span-full">
        <Button type="submit" loading={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

export default function NotificationsSettingsPage() {
  return (
    <div className="space-y-6">
      <PreferencesCard />
      <Phones />
    </div>
  );
}

function PreferencesCard() {
  const { can, membership } = useSession();
  const { data } = useQuery({
    queryKey: useOrgKey("notification-preferences"),
    queryFn: () => api<NotificationPreferences>("/notifications/preferences"),
  });
  return (
    <Card>
      <CardHeader
        title="Notifications"
        description={`Your personal alert settings for ${membership?.organisation_name ?? "this organisation"}.`}
      />
      {!can("alerts:read") ? (
        <Callout tone="info">Your role doesn&apos;t receive security alerts.</Callout>
      ) : !data ? (
        <Skeleton className="h-24" />
      ) : (
        <PreferencesForm initial={data} />
      )}
      <p className="mt-5 text-[13px] text-muted">SMS and WhatsApp alerts are planned.</p>
    </Card>
  );
}

function Phones() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["push-devices"],
    queryFn: () => api<PushDevice[]>("/me/push-devices", { org: false }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/me/push-devices/${id}`, { method: "DELETE", org: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["push-devices"] });
      toast("success", "Phone removed. It won't receive pushes until you sign in on it again.");
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
  const test = useMutation({
    mutationFn: () => api<{ message: string }>("/me/push-devices/test", { method: "POST", org: false }),
    onSuccess: (r) => toast("success", r.message),
    onError: (e) => toast("error", errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader
        title="Your phones"
        description="Phones signed in to the mobile app with your account. Signing out on a phone stops its notifications."
        action={
          data && data.length > 0 ? (
            <Button size="sm" variant="secondary" loading={test.isPending} onClick={() => test.mutate()}>
              Send a test
            </Button>
          ) : undefined
        }
      />
      {!data ? (
        <Skeleton className="h-16" />
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">
          No phones yet. Install the SME Cybersecurity Monitoring app on Android or iPhone, sign in and allow
          notifications.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {data.map((d) => (
            <li key={d.id} className="flex items-center gap-3 py-3">
              <Smartphone className="size-4 shrink-0 text-muted" />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-fg">
                  {d.device_name || (d.platform === "ios" ? "iPhone" : "Android phone")}
                  {!d.enabled && <Badge tone="warning">Not receiving</Badge>}
                </span>
                <span className="block text-[13px] text-muted">
                  {d.platform === "ios" ? "iOS" : "Android"}
                  {d.app_version && ` · app ${d.app_version}`} · last seen {timeAgo(d.last_seen_at)}
                  {d.last_error && ` · ${d.last_error}`}
                </span>
              </span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Remove ${d.device_name ?? "phone"}`}
                loading={remove.isPending && remove.variables === d.id}
                onClick={() => remove.mutate(d.id)}
              >
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
