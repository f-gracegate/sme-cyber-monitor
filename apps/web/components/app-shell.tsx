"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  ChevronDown,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  ScanSearch,
  Server,
  Settings,
  ShieldAlert,
  Siren,
  Sun,
  Users,
  Wrench,
  X,
  Building2,
  Inbox,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NotificationBell } from "@/components/notification-bell";
import { PoweredBy, ProductMark } from "@/components/powered-by";
import { toggleTheme } from "@/components/providers";
import { useSession } from "@/components/session";
import { Avatar, cn } from "@/components/ui";
import { api } from "@/lib/api";

type NavItem = { href: string; label: string; icon: LucideIcon; permission?: string; soon?: boolean };

const NAV: { title?: string; items: NavItem[] }[] = [
  {
    items: [
      { href: "/overview", label: "Overview", icon: LayoutDashboard },
      { href: "/assets", label: "Assets", icon: Server, permission: "assets:read" },
      { href: "/monitoring", label: "Monitoring", icon: Activity, permission: "monitoring:read" },
    ],
  },
  {
    title: "Detect & respond",
    items: [
      { href: "/findings", label: "Findings", icon: ScanSearch, permission: "findings:read" },
      { href: "/alerts", label: "Alerts", icon: Bell, permission: "alerts:read" },
      { href: "/incidents", label: "Incidents", icon: Siren, soon: true },
      { href: "/remediation", label: "Remediation", icon: Wrench, soon: true },
      { href: "/reports", label: "Reports", icon: FileText, soon: true },
    ],
  },
  {
    title: "Organisation",
    items: [
      { href: "/team", label: "Team", icon: Users, permission: "members:read" },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { can, me } = useSession();
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4" aria-label="Main">
      {NAV.map((section, i) => (
        <div key={i}>
          {section.title && (
            <p className="mb-1.5 px-3 text-[11px] font-medium tracking-wider text-sidebar-muted uppercase">
              {section.title}
            </p>
          )}
          <ul className="space-y-0.5">
            {section.items
              .filter((item) => !item.permission || can(item.permission))
              .map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                        active
                          ? "bg-sidebar-active font-medium text-white"
                          : "text-sidebar-text hover:bg-sidebar-active/60 hover:text-white",
                      )}
                    >
                      <Icon className={cn("size-[18px]", active ? "text-blue-400" : "")} aria-hidden />
                      <span className="flex-1">{item.label}</span>
                      {item.soon && (
                        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-sidebar-muted">
                          Soon
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
      {me.user.is_platform_admin && (
        <div>
          <p className="mb-1.5 px-3 text-[11px] font-medium tracking-wider text-sidebar-muted uppercase">
            Platform
          </p>
          <Link
            href="/platform"
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
              pathname.startsWith("/platform")
                ? "bg-sidebar-active font-medium text-white"
                : "text-sidebar-text hover:bg-sidebar-active/60 hover:text-white",
            )}
          >
            <ShieldAlert className="size-[18px]" aria-hidden />
            Customer organisations
          </Link>
          {process.env.NODE_ENV === "development" && (
            <Link
              href="/dev/mailbox"
              onClick={onNavigate}
              className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text hover:bg-sidebar-active/60 hover:text-white"
            >
              <Inbox className="size-[18px]" aria-hidden />
              Dev mailbox
            </Link>
          )}
        </div>
      )}
    </nav>
  );
}

function ApiStatus() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: () => fetch("/api/health").then((r) => r.json() as Promise<{ status: string }>),
    refetchInterval: 60_000,
  });
  const online = !isError && data?.status === "ok";
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-sidebar-muted">
      <span
        className={cn("size-1.5 rounded-full", online ? "bg-green-400" : "bg-amber-400")}
        aria-hidden
      />
      {online ? "Online" : data || isError ? "Degraded" : "Connecting"}
    </span>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex items-center justify-between border-b border-sidebar-border px-5 py-4">
        <ProductMark inverted />
      </div>
      <div className="px-5 pt-3">
        <ApiStatus />
      </div>
      <NavLinks onNavigate={onNavigate} />
      <div className="border-t border-sidebar-border px-5 py-4">
        <PoweredBy inverted />
      </div>
    </div>
  );
}

function OrgSwitcher() {
  const { me, orgId, switchOrg } = useSession();
  if (me.memberships.length === 0) return null;
  const current = me.memberships.find((m) => m.organisation_id === orgId);
  return (
    <label className="relative flex min-w-0 items-center gap-2">
      <Building2 className="size-4 shrink-0 text-subtle" aria-hidden />
      <span className="sr-only">Organisation</span>
      <select
        value={orgId ?? ""}
        onChange={(e) => switchOrg(e.target.value)}
        className="max-w-[16rem] min-w-0 appearance-none truncate rounded-lg bg-transparent py-1.5 pr-7 pl-1 text-sm font-semibold text-fg hover:bg-surface-2 focus:outline-none"
      >
        {me.memberships.map((m) => (
          <option key={m.organisation_id} value={m.organisation_id}>
            {m.organisation_name}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-1.5 size-4 text-subtle" aria-hidden />
      {current && (
        <span className="hidden truncate text-xs text-subtle lg:inline">{current.role_label}</span>
      )}
    </label>
  );
}

function UserMenu() {
  const { me } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST", org: false, noRefresh: true }),
    onSettled: () => {
      // Drop every cached response so nothing from this session survives sign-out.
      queryClient.clear();
      router.replace("/login");
    },
  });

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const name = me.user.full_name || me.user.email;
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-lg p-1 hover:bg-surface-2"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Avatar name={name} />
        <span className="hidden text-left text-sm leading-tight md:block">
          <span className="block font-medium text-fg">{name}</span>
          <span className="block text-xs text-subtle">{me.user.email}</span>
        </span>
        <ChevronDown className="hidden size-4 text-subtle md:block" aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-border bg-surface p-1.5 shadow-lg"
        >
          <Link
            role="menuitem"
            href="/settings/security"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-fg hover:bg-surface-2"
          >
            <Settings className="size-4 text-subtle" /> Account security
          </Link>
          <Link
            role="menuitem"
            href="/onboarding"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-fg hover:bg-surface-2"
          >
            <Building2 className="size-4 text-subtle" /> New organisation
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={() => logout.mutate()}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-fg hover:bg-surface-2"
          >
            <LogOut className="size-4 text-subtle" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Sidebar />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-slate-950/60" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85%] shadow-xl">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute top-4 right-3 z-10 rounded-md p-1 text-sidebar-text hover:bg-sidebar-active"
              aria-label="Close menu"
            >
              <X className="size-5" />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur sm:px-6">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="rounded-md p-1.5 text-muted hover:bg-surface-2 lg:hidden"
          aria-label="Open menu"
        >
          <Menu className="size-5" />
        </button>
        <div className="min-w-0 flex-1">
          <OrgSwitcher />
        </div>
        <NotificationBell />
        <button
          type="button"
          onClick={toggleTheme}
          className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
          aria-label="Toggle dark mode"
          title="Toggle dark mode"
        >
          <Moon className="size-[18px] dark:hidden" />
          <Sun className="hidden size-[18px] dark:block" />
        </button>
        <UserMenu />
      </header>

      <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:py-8">{children}</main>
    </div>
  );
}
