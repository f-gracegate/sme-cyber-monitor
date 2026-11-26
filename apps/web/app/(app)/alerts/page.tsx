import { Bell } from "lucide-react";
import type { Metadata } from "next";
import { ModulePreview } from "@/components/module-preview";

export const metadata: Metadata = { title: "Alerts" };

export default function Page() {
  return (
    <ModulePreview
      title="Alerts"
      description="Suspicious activity that needs attention, deduplicated and prioritised."
      phase="Phases 2–5"
      icon={<Bell className="size-5" />}
      dependsOn="Alerts depend on monitoring and detection rules, which are being built in the next phases."
      capabilities={[
        "Filter by severity: Critical, High, Medium, Low, Informational",
        "Filter by status: New, Acknowledged, Investigating, Resolved",
        "What happened, which asset, why it matters and what to do next",
        "Grouping so one repeated event never becomes thousands of alerts",
        "Email and mobile push notifications",
      ]}
    />
  );
}
