import { Siren } from "lucide-react";
import type { Metadata } from "next";
import { ModulePreview } from "@/components/module-preview";

export const metadata: Metadata = { title: "Incidents" };

export default function Page() {
  return (
    <ModulePreview
      title="Incidents"
      description="Coordinate investigations from first alert to verified resolution."
      phase="Phase 5"
      icon={<Siren className="size-5" />}
      dependsOn="Incident management is scheduled after alerting is in place."
      capabilities={[
        "Incident summary, severity and affected assets",
        "Timeline of related alerts and actions",
        "Evidence and investigation notes",
        "Assigned analyst, containment and remediation actions",
        "Resolution and closure reason",
      ]}
    />
  );
}
