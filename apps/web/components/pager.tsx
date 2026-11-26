"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui";

export function Pager({
  page,
  total,
  pageSize,
  noun,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  noun: [string, string];
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 text-sm text-muted">
      <span>
        {total} {total === 1 ? noun[0] : noun[1]}
      </span>
      {pages > 1 && (
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
            <ChevronLeft className="size-4" />
          </Button>
          <span>
            Page {page} of {pages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
