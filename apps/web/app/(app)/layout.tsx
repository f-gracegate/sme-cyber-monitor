import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { SessionGate } from "@/components/session";
import { Spinner } from "@/components/ui";

// The signed-in workspace renders in the browser once the session is confirmed, so its pages
// cannot be part of a prerendered shell. Opt this segment out of instant-navigation checks.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Spinner className="size-6" />
        </div>
      }
    >
      <SessionGate>
        <AppShell>{children}</AppShell>
      </SessionGate>
    </Suspense>
  );
}
