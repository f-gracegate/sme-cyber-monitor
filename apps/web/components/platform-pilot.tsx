"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Card, CardHeader, EmptyState, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { FeedbackItem, PilotOrg } from "@/lib/types";

const pct = (v: number | null) => (v === null ? "—" : `${v}%`);
const num = (v: number | null, unit: string) => (v === null ? "—" : `${v} ${unit}`);

/** The pilot measurements from the product plan, per customer. Counts and timings only. */
export function PilotMetrics() {
  const { data, isPending } = useQuery({
    queryKey: ["platform", "pilot-metrics"],
    queryFn: () => api<{ organisations: PilotOrg[] }>("/platform/pilot-metrics", { org: false }),
  });
  return (
    <Card padded={false}>
      <div className="p-5 pb-1">
        <CardHeader
          title="Pilot measurements"
          description="Monitoring coverage, agent reporting, detection accuracy (alerts marked “not a real problem”), response times, usage and willingness to pay. Last 30 days."
        />
      </div>
      {isPending ? (
        <div className="p-5">
          <Skeleton className="h-32" />
        </div>
      ) : !data?.organisations.length ? (
        <EmptyState title="No organisations yet" />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <thead>
              <tr>
                <Th>Organisation</Th>
                <Th>Plan</Th>
                <Th>Assets monitored</Th>
                <Th>Agents reporting</Th>
                <Th>Alerts</Th>
                <Th>False positives</Th>
                <Th>Time to acknowledge</Th>
                <Th>Time to resolve</Th>
                <Th>Active users (7 days)</Th>
                <Th>Feedback</Th>
              </tr>
            </thead>
            <tbody>
              {data.organisations.map((o) => (
                <tr key={o.organisation_id}>
                  <Td className="font-medium text-fg">{o.name}</Td>
                  <Td>
                    <span className="capitalize">{o.plan}</span>{" "}
                    <Badge tone={o.paying ? "success" : o.subscription === "expired" ? "critical" : "neutral"}>
                      {o.paying ? "Paying" : o.subscription}
                    </Badge>
                  </Td>
                  <Td className="tabular-nums">
                    {pct(o.assets_monitored_pct)} <span className="text-subtle">of {o.assets}</span>
                  </Td>
                  <Td className="tabular-nums">
                    {pct(o.agents_reporting_pct)} <span className="text-subtle">of {o.agents_enrolled}</span>
                  </Td>
                  <Td className="tabular-nums">{o.alerts_30d}</Td>
                  <Td className="tabular-nums">{pct(o.false_positive_pct)}</Td>
                  <Td className="tabular-nums">{num(o.median_minutes_to_acknowledge, "min")}</Td>
                  <Td className="tabular-nums">{num(o.median_hours_to_resolve, "h")}</Td>
                  <Td className="tabular-nums">
                    {o.active_users_7d} <span className="text-subtle">of {o.members}</span>
                  </Td>
                  <Td className="tabular-nums">{o.feedback_count}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </Card>
  );
}

const KIND: Record<string, { label: string; tone: "info" | "critical" | "success" | "neutral" }> = {
  idea: { label: "Idea", tone: "info" },
  problem: { label: "Problem", tone: "critical" },
  praise: { label: "Praise", tone: "success" },
  question: { label: "Question", tone: "neutral" },
};

export function FeedbackInbox() {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["platform", "feedback"],
    queryFn: () => api<FeedbackItem[]>("/platform/feedback", { org: false }),
  });
  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api(`/platform/feedback/${id}`, { method: "PATCH", body: { status }, org: false }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["platform", "feedback"] }),
  });
  return (
    <Card padded={false}>
      <div className="p-5 pb-1">
        <CardHeader title="Customer feedback" description="Sent from the feedback button inside the product." />
      </div>
      {isPending ? (
        <div className="p-5">
          <Skeleton className="h-24" />
        </div>
      ) : !data?.length ? (
        <EmptyState title="No feedback yet" />
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {data.map((f) => (
            <li key={f.id} className="flex flex-wrap items-start gap-3 px-5 py-3">
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
                  <Badge tone={KIND[f.kind]?.tone ?? "neutral"}>{KIND[f.kind]?.label ?? f.kind}</Badge>
                  {f.rating && <span>Rated {f.rating}/5</span>}
                  <span>
                    {f.user_name ?? "Someone"}
                    {f.organisation_name ? ` · ${f.organisation_name}` : ""} · {timeAgo(f.created_at)}
                    {f.page ? ` · on ${f.page}` : ""}
                  </span>
                </span>
                <span className="mt-1 block text-sm whitespace-pre-line text-fg">{f.message}</span>
              </span>
              <Select
                aria-label="Feedback status"
                value={f.status}
                onChange={(e) => update.mutate({ id: f.id, status: e.target.value })}
                className="w-32"
              >
                <option value="new">New</option>
                <option value="reviewed">Reviewed</option>
                <option value="done">Done</option>
              </Select>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
