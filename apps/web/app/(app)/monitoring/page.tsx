import { Activity } from "lucide-react";
import type { Metadata } from "next";
import { ModulePreview } from "@/components/module-preview";

export const metadata: Metadata = { title: "Monitoring" };

export default function Page() {
  return (
    <ModulePreview
      title="Monitoring"
      description="Scheduled and event-driven checks across your websites, computers, servers and networks."
      phase="Phases 2–4"
      icon={<Activity className="size-5" />}
      dependsOn="Website and domain monitoring arrives first, followed by endpoint agents and the on-premises network collector. Register and authorise your assets now so they're ready."
      capabilities={[
        "Website uptime, response time and TLS certificate checks",
        "DNS record and nameserver change detection",
        "Security header and exposed-service checks for authorised sites",
        "Endpoint agent health and heartbeat for Windows, macOS and Linux",
        "Network collector health, firewall and router availability",
        "Clear coverage view of what is and isn’t monitored",
      ]}
    />
  );
}
