import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { SecuritySettings } from "./security-settings";

export default function SecurityPage() {
  return (
    <Suspense fallback={<Skeleton className="h-80" />}>
      <SecuritySettings />
    </Suspense>
  );
}
