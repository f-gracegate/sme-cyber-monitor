import type { Metadata } from "next";
import Link from "next/link";
import { PoweredBy, ProductMark } from "@/components/powered-by";

export const metadata: Metadata = { title: "Privacy Notice" };

export default function Page() {
  return (
    <div className="mx-auto max-w-2xl px-5 py-10">
      <Link href="/login">
        <ProductMark />
      </Link>
      <h1 className="mt-10 text-2xl font-semibold tracking-tight">Privacy Notice</h1>
      <p className="mt-1 text-sm text-muted">How we handle personal data under Ghana’s Data Protection Act, 2012 (Act 843).</p>
      <div className="mt-6 rounded-[var(--radius-control)] border border-warning/30 bg-warning-soft p-4 text-sm text-warning-text">
        Draft summary for the pilot programme. The full legal text will be published after legal
        review and before commercial launch.
      </div>
      <ul className="mt-6 list-disc space-y-3 pl-5 text-sm leading-relaxed">
          <li>We process account details (name, email, role) and the security information your organisation chooses to send us, only to provide the service.</li>
          <li>Each customer organisation’s data is kept separate from every other organisation’s.</li>
          <li>Your organisation is the data controller for employee and device data it sends; we act as its processor under a data-processing agreement.</li>
          <li>Security logs are kept only as long as your plan’s retention period, then deleted.</li>
          <li>You can ask for access to, correction of, or deletion of your personal data.</li>
      </ul>
      <div className="mt-12">
        <PoweredBy />
      </div>
    </div>
  );
}
