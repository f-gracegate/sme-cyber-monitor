import { FileText } from "lucide-react";
import type { Metadata } from "next";
import { ModulePreview } from "@/components/module-preview";

export const metadata: Metadata = { title: "Reports" };

export default function Page() {
  return (
    <ModulePreview
      title="Reports"
      description="Management-ready security reports."
      phase="Phase 5"
      icon={<FileText className="size-5" />}
      dependsOn="Reports use monitoring, findings and incident data, so they follow those modules."
      capabilities={[
        "Executive security summary",
        "Asset inventory and monitoring coverage",
        "Endpoint health",
        "Vulnerability and configuration findings",
        "Incident history and remediation progress",
        "Monthly report emailed to owners",
      ]}
    />
  );
}
