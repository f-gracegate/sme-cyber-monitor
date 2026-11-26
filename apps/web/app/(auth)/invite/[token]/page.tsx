import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { InviteView } from "./invite-view";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-40" />}>
      <InviteView />
    </Suspense>
  );
}
