import type { Metadata } from "next";
import Link from "next/link";
import { PoweredBy, ProductMark } from "@/components/powered-by";

export const metadata: Metadata = { title: "Terms of Service" };

export default function Page() {
  return (
    <div className="mx-auto max-w-2xl px-5 py-10">
      <Link href="/login">
        <ProductMark />
      </Link>
      <h1 className="mt-10 text-2xl font-semibold tracking-tight">Terms of Service</h1>
      <p className="mt-1 text-sm text-muted">The rules for using the platform.</p>
      <div className="mt-6 rounded-[var(--radius-control)] border border-warning/30 bg-warning-soft p-4 text-sm text-warning-text">
        Pilot version. The full terms and data-processing agreement will be published after legal
        review and before commercial launch.
      </div>
      <ul className="mt-6 list-disc space-y-3 pl-5 text-sm leading-relaxed">
          <li>Only register and monitor assets your organisation owns or is authorised to monitor.</li>
          <li>Keep your login details private and use multi-factor authentication for administrator accounts.</li>
          <li>Monitoring and alerts support your security decisions; they don’t guarantee that no incident will occur.</li>
          <li>Managed monitoring or response services, where offered, are subject to applicable Cyber Security Authority licensing.</li>
          <li>Plans are prepaid monthly or yearly in Ghana cedis, with no automatic charges. If a plan lapses, your data and existing monitoring are kept, but you can’t add assets, people or devices until you renew.</li>
          <li>Install the endpoint agent and network collector only on equipment your organisation controls, and tell staff that their work devices are monitored, as your employment policies require.</li>
          <li>Don’t use the platform to probe, test or monitor systems you don’t have permission for, or to disrupt the service for others.</li>
          <li>You can export your data and delete your organisation at any time from Settings → Data and privacy.</li>
      </ul>
      <div className="mt-12">
        <PoweredBy />
      </div>
    </div>
  );
}
