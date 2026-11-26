"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { AssetIcon } from "@/components/asset-badges";
import { FindingStatusBadge, SeverityBadge, severityBarClass } from "@/components/monitoring-ui";
import { cn } from "@/components/ui";
import { timeAgo } from "@/lib/format";
import { checkTypeLabel } from "@/lib/labels";
import type { Finding } from "@/lib/types";

export function FindingList({ findings }: { findings: Finding[] }) {
  return (
    <ul className="divide-y divide-border">
      {findings.map((f) => (
        <li key={f.id}>
          <Link href={`/findings/${f.id}`} className="group flex items-stretch gap-4 px-4 py-3.5 hover:bg-surface-2/60">
            <span className={cn("w-1 shrink-0 rounded-full", severityBarClass(f.severity))} aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-fg group-hover:text-primary-text">{f.title}</span>
                <SeverityBadge severity={f.severity} />
                {f.status !== "open" && <FindingStatusBadge status={f.status} />}
              </span>
              <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                {f.asset && (
                  <span className="inline-flex items-center gap-1.5">
                    <AssetIcon type={f.asset.type} className="size-3.5" /> {f.asset.name}
                  </span>
                )}
                <span>{checkTypeLabel(f.check_type)}</span>
                <span>Last seen {timeAgo(f.last_seen_at)}</span>
                {f.occurrences > 1 && <span>Seen {f.occurrences}×</span>}
              </span>
            </span>
            <ChevronRight className="size-4 shrink-0 self-center text-subtle" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
