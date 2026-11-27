"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "@/components/session";
import { PageHeader, cn } from "@/components/ui";

const SECTIONS = [
  { href: "/settings", label: "Business profile", permission: "org:read", exact: true },
  { href: "/settings/security", label: "Security & MFA" },
  { href: "/settings/notifications", label: "Notifications", permission: "org:read" },
  { href: "/settings/departments", label: "Departments", permission: "org:read" },
  { href: "/settings/integrations", label: "Integrations", permission: "org:update" },
  { href: "/settings/subscription", label: "Subscription", permission: "billing:read" },
  { href: "/settings/muted-alerts", label: "Muted alerts", permission: "alerts:read" },
  { href: "/settings/privacy", label: "Data and privacy" },
  { href: "/settings/audit", label: "Audit history", permission: "audit:read" },
];
const LATER: string[] = [];

export default function SettingsLayout({ children }: LayoutProps<"/settings">) {
  const pathname = usePathname();
  const { can, membership } = useSession();
  return (
    <>
      <PageHeader title="Settings" description="Manage your organisation and your own account." />
      <div className="grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Settings" className="-mx-1 flex gap-1 overflow-x-auto lg:flex-col">
          {SECTIONS.filter((s) => !s.permission || (membership && can(s.permission))).map((s) => {
            const active = s.exact ? pathname === s.href : pathname.startsWith(s.href);
            return (
              <Link
                key={s.href}
                href={s.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-lg px-3 py-2 text-sm whitespace-nowrap",
                  active ? "bg-surface font-medium text-fg shadow-sm ring-1 ring-border" : "text-muted hover:bg-surface-2 hover:text-fg",
                )}
              >
                {s.label}
              </Link>
            );
          })}
          {LATER.map((l) => (
            <span key={l} className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm whitespace-nowrap text-subtle">
              {l}
              <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px]">Soon</span>
            </span>
          ))}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </>
  );
}
