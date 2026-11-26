import { ScanSearch } from "lucide-react";
import type { Metadata } from "next";
import { ModulePreview } from "@/components/module-preview";

export const metadata: Metadata = { title: "Findings" };

export default function Page() {
  return (
    <ModulePreview
      title="Findings"
      description="Security weaknesses and misconfigurations discovered by monitoring."
      phase="Phase 2"
      icon={<ScanSearch className="size-5" />}
      dependsOn="Findings are generated from monitoring data, so they start appearing once website monitoring is switched on."
      capabilities={[
        "Plain-English explanation of each issue and why it matters",
        "Severity from Critical to Informational",
        "Affected asset and supporting evidence",
        "Recommended fix and owner assignment",
      ]}
    />
  );
}
