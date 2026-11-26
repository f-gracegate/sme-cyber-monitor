"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOrgKey, useSession } from "@/components/session";
import { useToast } from "@/components/providers";
import { Button, Callout, Card, CardHeader, Field, Select, Skeleton } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { NotificationPreferences } from "@/lib/types";
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
      className="grid gap-5 sm:grid-cols-2"
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
      <div className="sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

export default function NotificationsSettingsPage() {
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
      <p className="mt-5 text-[13px] text-muted">
        Mobile push notifications arrive with the Android and iOS apps. SMS and WhatsApp alerts
        are planned.
      </p>
    </Card>
  );
}
