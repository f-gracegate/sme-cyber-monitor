import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { SandboxCheckout } from "./view";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <SandboxCheckout />
    </Suspense>
  );
}
