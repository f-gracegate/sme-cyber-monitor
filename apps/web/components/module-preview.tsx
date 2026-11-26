import { CircleDashed } from "lucide-react";
import type { ReactNode } from "react";
import { Badge, Card, PageHeader } from "@/components/ui";

/** A module that's specified but not built yet. Says so plainly and shows what's coming. */
export function ModulePreview({
  title,
  description,
  phase,
  icon,
  capabilities,
  dependsOn,
}: {
  title: string;
  description: string;
  phase: string;
  icon: ReactNode;
  capabilities: string[];
  dependsOn: string;
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card className="max-w-3xl">
        <div className="flex items-start gap-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-text">
            {icon}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-semibold">Not available yet</h2>
              <Badge tone="primary">{phase}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted">{dependsOn}</p>
            <h3 className="mt-5 text-xs font-medium tracking-wide text-subtle uppercase">
              What this module will do
            </h3>
            <ul className="mt-2 space-y-2">
              {capabilities.map((c) => (
                <li key={c} className="flex gap-2.5 text-sm">
                  <CircleDashed className="mt-0.5 size-4 shrink-0 text-subtle" aria-hidden />
                  {c}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>
    </>
  );
}
