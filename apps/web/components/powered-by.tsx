import Image from "next/image";
import { brand } from "@/lib/brand";
import { cn } from "@/lib/cn";

export function PoweredBy({ className, inverted }: { className?: string; inverted?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span
        className={cn(
          "text-[11px] tracking-wide uppercase",
          inverted ? "text-sidebar-muted" : "text-subtle",
        )}
      >
        Powered by
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Image
          src={brand.poweredByLogo}
          alt=""
          width={20}
          height={20}
          className="size-5 rounded-[4px] bg-white object-contain"
        />
        <span className={cn("text-xs font-semibold", inverted ? "text-white" : "text-fg")}>
          {brand.poweredByName}
        </span>
      </span>
    </div>
  );
}

export function ProductMark({ inverted, compact }: { inverted?: boolean; compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-primary text-white shadow-sm">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
          <path
            d="M12 2.5 4 5.5v6c0 5 3.4 8.9 8 10 4.6-1.1 8-5 8-10v-6l-8-3Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path
            d="m8.5 12 2.5 2.5 4.5-5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {!compact && (
        <span className="min-w-0 leading-tight">
          <span
            className={cn("block text-sm font-semibold", inverted ? "text-white" : "text-fg")}
          >
            {brand.shortName}
          </span>
          <span
            className={cn("block text-[11px]", inverted ? "text-sidebar-muted" : "text-subtle")}
          >
            Security workspace
          </span>
        </span>
      )}
    </div>
  );
}
