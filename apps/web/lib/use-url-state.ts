"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/** Read and write list filters in the URL so filtered views can be shared and bookmarked. */
export function useUrlState() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const set = useCallback(
    (changes: Record<string, string | string[] | null>, keepPage = false) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(changes)) {
        next.delete(key);
        if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
        else if (value) next.set(key, value);
      }
      if (!keepPage && !("page" in changes)) next.delete("page");
      router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
    },
    [params, pathname, router],
  );

  return {
    get: (key: string) => params.get(key) ?? "",
    getAll: (key: string) => params.getAll(key),
    page: Math.max(1, Number(params.get("page") ?? 1)),
    set,
  };
}
