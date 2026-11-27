import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { PaymentReturn } from "./view";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <PaymentReturn />
    </Suspense>
  );
}
