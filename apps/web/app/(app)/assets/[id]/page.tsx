import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { AssetDetailView } from "./asset-detail";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <AssetDetailView />
    </Suspense>
  );
}
