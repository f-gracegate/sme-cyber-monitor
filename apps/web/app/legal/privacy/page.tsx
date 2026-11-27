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
        Pilot version. This notice will be reviewed by a lawyer, and our registration with the Data
        Protection Commission confirmed, before commercial launch.
      </div>
      <Section title="Who we are and our role">
        <p>
          SME Cybersecurity Monitoring is provided by GraceGate Technologies. For the security information your
          organisation sends us (devices, sign-in events, network logs, employee names in those records) your
          organisation is the <strong>data controller</strong> and we are its <strong>data processor</strong>, acting
          only on its instructions under a data-processing agreement. For your own account details and billing we are
          the controller.
        </p>
      </Section>
      <Section title="What we process">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Account details: name, email, username, role, sign-in history, and whether two-step sign-in is on.</li>
          <li>What your organisation registers and sends: websites, domains, devices, their security health, security events and network logs.</li>
          <li>Incident records, evidence you upload, tasks, reports and the audit history of actions in the product.</li>
          <li>Mobile app: a push notification token per phone. Billing: plan, amounts and the last digits of a card or wallet (card numbers and PINs go to our payment partner, never to us).</li>
        </ul>
      </Section>
      <Section title="Why, and who else is involved">
        <p>
          Only to provide the monitoring service, keep it secure, bill for it and support you. We don’t sell data or use
          it for advertising. Service providers we rely on: our hosting provider, Paystack (payments), Google Firebase
          (phone notifications, which show only an alert’s severity and title), and our email provider. Each is bound
          by contract to protect the data.
        </p>
      </Section>
      <Section title="How long we keep it">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Raw monitoring data (security events, check results): your organisation’s retention setting, 7 to 365 days depending on plan. Default 30 days.</li>
          <li>Notifications: 180 days. Data exports: 7 days.</li>
          <li>Findings, alerts, incidents and reports: while your organisation is a customer.</li>
          <li>When an organisation is deleted, its data is erased after a 30-day cooling-off period. Audit history and billing records are kept, without names where possible, because the law requires them.</li>
        </ul>
      </Section>
      <Section title="Security">
        <p>
          Each organisation’s data is isolated at the database level. Data is encrypted in transit and at rest; evidence,
          reports and exports are encrypted individually. Passwords are hashed with Argon2id. Staff access is limited
          and recorded.
        </p>
      </Section>
      <Section title="Your rights">
        <p>
          You can ask for access to, correction of, or deletion of your personal data, and object to processing.
          Owners and administrators can export all organisation data and delete the organisation under{" "}
          <em>Settings → Data and privacy</em>; anyone can delete their own account there. Employees whose data an
          organisation sends us should contact that organisation first. You may complain to the Data Protection
          Commission of Ghana.
        </p>
      </Section>
      <p className="mt-8 text-[13px] text-muted">Contact: privacy@gracegate.example. Last updated 27 November 2026.</p>
      <div className="mt-12">
        <PoweredBy />
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-7 text-sm leading-relaxed">
      <h2 className="mb-2 text-base font-semibold text-fg">{title}</h2>
      {children}
    </section>
  );
}

