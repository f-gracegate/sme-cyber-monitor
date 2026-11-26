import {
  BrickWall,
  Cloud,
  Globe,
  Laptop,
  Monitor,
  Network,
  Router,
  Server,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui";
import { MONITORING_STATUS, type Tone } from "@/lib/labels";

const ICONS: Record<string, LucideIcon> = {
  website: Globe,
  domain: Globe,
  workstation: Monitor,
  laptop: Laptop,
  server: Server,
  firewall: BrickWall,
  router: Router,
  switch: Network,
  network_device: Network,
  cloud_account: Cloud,
  cloud_service: Cloud,
};

export function AssetIcon({ type, className }: { type: string; className?: string }) {
  const Icon = ICONS[type] ?? Server;
  return <Icon className={className ?? "size-4"} aria-hidden />;
}

export function MonitoringBadge({ status }: { status: string }) {
  const meta = MONITORING_STATUS[status] ?? { label: status, tone: "neutral" as Tone };
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
}

const CRIT_TONE: Record<string, Tone> = {
  low: "neutral",
  medium: "info",
  high: "high",
  critical: "critical",
};

export function CriticalityBadge({ level }: { level: string }) {
  return <Badge tone={CRIT_TONE[level] ?? "neutral"}>{level[0].toUpperCase() + level.slice(1)}</Badge>;
}

export function RiskBadge({ level }: { level: string }) {
  if (level === "unknown") return <span className="text-sm text-subtle">Not assessed</span>;
  return <CriticalityBadge level={level} />;
}
