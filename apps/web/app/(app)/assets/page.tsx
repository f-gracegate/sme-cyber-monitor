import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { AssetInventory } from "./asset-inventory";

export const metadata: Metadata = { title: "Assets" };

export default function AssetsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <AssetInventory />
    </Suspense>
  );
}
