import { CircleAlert, Lightbulb, ListChecks, Search } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { AssetIcon } from "@/components/asset-badges";
import { EvidenceList } from "@/components/monitoring-ui";
import { Card } from "@/components/ui";
import { formatDateTime, timeAgo } from "@/lib/format";
import { checkTypeLabel } from "@/lib/labels";
import type { Finding } from "@/lib/types";

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="flex gap-3">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <div className="mt-1 text-sm text-muted">{children}</div>
      </div>
    </section>
  );
}

/** The plain-English story of a finding: what, why, what next, and the evidence behind it. */
export function FindingExplainer({ finding }: { finding: Finding }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <Card className="space-y-6">
        <Section icon={<CircleAlert className="size-4" />} title="What happened">
          {finding.description}
        </Section>
        <Section icon={<Lightbulb className="size-4" />} title="Why it matters">
          {finding.impact}
        </Section>
        <Section icon={<ListChecks className="size-4" />} title="What to do next">
          <span className="text-fg">{finding.recommendation}</span>
        </Section>
        <Section icon={<Search className="size-4" />} title="Evidence">
          <div className="mt-2">
            <EvidenceList evidence={finding.evidence} />
          </div>
        </Section>
      </Card>
      <Card>
        <dl className="space-y-4 text-sm">
          {finding.asset && (
            <div>
              <dt className="text-xs font-medium tracking-wide text-subtle uppercase">Affected asset</dt>
              <dd className="mt-1">
                <Link href={`/assets/${finding.asset.id}`} className="inline-flex items-center gap-2 font-medium text-primary-text hover:underline">
                  <AssetIcon type={finding.asset.type} /> {finding.asset.name}
                </Link>
                <span className="block font-mono text-xs text-subtle">{finding.asset.identifier}</span>
              </dd>
            </div>
          )}
          <div>
            <dt className="text-xs font-medium tracking-wide text-subtle uppercase">Detected by</dt>
            <dd className="mt-1">{checkTypeLabel(finding.check_type)} check</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-subtle uppercase">First seen</dt>
            <dd className="mt-1">{formatDateTime(finding.first_seen_at)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-subtle uppercase">Last seen</dt>
            <dd className="mt-1">
              {timeAgo(finding.last_seen_at)} · seen {finding.occurrences} time{finding.occurrences === 1 ? "" : "s"}
            </dd>
          </div>
          {finding.resolved_at && (
            <div>
              <dt className="text-xs font-medium tracking-wide text-subtle uppercase">Closed</dt>
              <dd className="mt-1">
                {formatDateTime(finding.resolved_at)}
                {finding.resolution_note && <span className="mt-1 block text-muted italic">&ldquo;{finding.resolution_note}&rdquo;</span>}
              </dd>
            </div>
          )}
        </dl>
      </Card>
    </div>
  );
}
