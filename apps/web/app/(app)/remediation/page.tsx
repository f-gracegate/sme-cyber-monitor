import { Wrench } from "lucide-react";
import type { Metadata } from "next";
import { ModulePreview } from "@/components/module-preview";

export const metadata: Metadata = { title: "Remediation" };

export default function Page() {
  return (
    <ModulePreview
      title="Remediation"
      description="Track the work needed to fix security issues."
      phase="Phase 5"
      icon={<Wrench className="size-5" />}
      dependsOn="Remediation tasks are created from findings and incidents."
      capabilities={[
        "Assign fixes to team members with due dates",
        "Track progress across the organisation",
        "Verify that a fix actually resolved the finding",
      ]}
    />
  );
}
