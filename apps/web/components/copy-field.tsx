"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <p className="mb-1 text-xs font-medium tracking-wide text-subtle uppercase">{label}</p>
      <div className="flex items-stretch overflow-hidden rounded-[var(--radius-control)] border border-border-strong bg-surface-2">
        <code className="min-w-0 flex-1 overflow-x-auto px-3 py-2 font-mono text-[13px] whitespace-nowrap text-fg">
          {value}
        </code>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            } catch {
              /* clipboard unavailable */
            }
          }}
          className="flex shrink-0 items-center gap-1.5 border-l border-border-strong px-3 text-xs font-medium text-muted hover:bg-surface hover:text-fg"
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}
