"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useOrgKey, useSession } from "@/components/session";
import { Callout } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Organisation } from "@/lib/types";

/** Everyone in an organisation that's scheduled for deletion should know, not just owners. */
export function DeletionBanner() {
  const { orgId, membership } = useSession();
  const { data } = useQuery({
    queryKey: useOrgKey("organisation"),
    queryFn: () => api<Organisation>(`/organisations/${orgId}`, { org: false }),
    enabled: !!orgId && !!membership,
    staleTime: 5 * 60_000,
  });
  if (!data?.deletion_scheduled_for) return null;
  return (
    <div className="mb-5">
      <Callout tone="critical" title={`${data.name} will be deleted on ${formatDate(data.deletion_scheduled_for)}`}>
        All of its monitoring data, alerts, incidents and evidence will be erased.{" "}
        {membership?.role === "owner" ? (
          <Link href="/settings/privacy" className="font-medium underline underline-offset-2">
            Cancel or export your data
          </Link>
        ) : (
          "Ask an owner if this is unexpected."
        )}
      </Callout>
    </div>
  );
}
