import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { View } from "./view";

export const metadata: Metadata = { title: "Incidents" };

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <View />
    </Suspense>
  );
}
