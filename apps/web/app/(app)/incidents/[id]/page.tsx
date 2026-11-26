import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { Detail } from "./detail";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Detail />
    </Suspense>
  );
}
