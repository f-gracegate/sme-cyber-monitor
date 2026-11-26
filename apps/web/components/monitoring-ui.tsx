"use client";

import { Check } from "lucide-react";
import { Badge, cn } from "@/components/ui";
import {
  ALERT_STATUS,
  CHECK_STATUS,
  FINDING_STATUS,
  SEVERITY_TONE,
  severityLabel,
} from "@/lib/labels";

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge tone={SEVERITY_TONE[severity] ?? "neutral"} dot>
      {severityLabel(severity)}
    </Badge>
  );
}

export function AlertStatusBadge({ status }: { status: string }) {
  const meta = ALERT_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function FindingStatusBadge({ status }: { status: string }) {
  const meta = FINDING_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function CheckStatusBadge({ status, enabled = true }: { status: string; enabled?: boolean }) {
  const meta = CHECK_STATUS[enabled ? status : "disabled"] ?? CHECK_STATUS.pending;
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
}

const SEVERITY_BAR: Record<string, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-warning",
  low: "bg-primary",
  informational: "bg-border-strong",
};

export function severityBarClass(severity: string) {
  return SEVERITY_BAR[severity] ?? "bg-border-strong";
}

/** Toggle chips for multi-select filters (severity, status). */
export function ChipFilter({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: readonly { value: string; label: string }[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-xs font-medium text-subtle">{label}</span>
      {options.map((o) => {
        const on = selected.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() =>
              onChange(on ? selected.filter((v) => v !== o.value) : [...selected, o.value])
            }
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
              on
                ? "border-primary bg-primary-soft text-primary-text"
                : "border-border-strong text-muted hover:bg-surface-2",
            )}
          >
            {on && <Check className="size-3" />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    return value
      .map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v)))
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function EvidenceList({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence ?? {});
  if (!entries.length) return <p className="text-sm text-subtle">No additional detail recorded.</p>;
  return (
    <dl className="divide-y divide-border rounded-[var(--radius-control)] border border-border">
      {entries.map(([k, v]) => (
        <div key={k} className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-[10rem_minmax(0,1fr)]">
          <dt className="text-subtle">{k.replace(/_/g, " ")}</dt>
          <dd className="font-mono text-[13px] break-words text-fg">{formatValue(v)}</dd>
        </div>
      ))}
    </dl>
  );
}
