"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff } from "lucide-react";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Card, CardHeader, EmptyState, Skeleton } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import type { SuppressionRule } from "@/lib/types";

export default function MutedAlertsPage() {
  const { can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("suppression-rules");
  const { data } = useQuery({ queryKey: key, queryFn: () => api<SuppressionRule[]>("/suppression-rules") });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/suppression-rules/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      toast("success", "Alerts of this kind will be raised again.");
    },
    onError: (e) => toast("error", errorMessage(e)),
  });
  return (
    <Card padded={false}>
      <div className="p-5 pb-1">
        <CardHeader
          title="Muted alerts"
          description="Kinds of alert your team decided not to be told about, usually because they're known and handled elsewhere. Findings are still recorded and still count in the posture score. Critical alerts can never be muted."
        />
      </div>
      {!data ? (
        <div className="p-4">
          <Skeleton className="h-24" />
        </div>
      ) : data.length === 0 ? (
        <EmptyState icon={<BellOff className="size-5" />} title="Nothing is muted" description="Mute an alert while resolving it if it's not a real problem for you." />
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-fg">
                  {r.rule_title} · {r.asset_name ?? "all assets"}
                </span>
                <span className="block text-[13px] text-muted">
                  &ldquo;{r.reason}&rdquo; · {r.created_by_name ?? "Someone"} · {r.expires_at ? `until ${formatDate(r.expires_at)}` : "no end date"} ·{" "}
                  {r.hits ? `held back ${r.hits} time${r.hits === 1 ? "" : "s"}, last ${timeAgo(r.last_hit_at)}` : "not triggered yet"}
                </span>
              </span>
              {can("alerts:manage") && (
                <Button size="sm" variant="secondary" loading={remove.isPending && remove.variables === r.id} onClick={() => remove.mutate(r.id)}>
                  Unmute
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
