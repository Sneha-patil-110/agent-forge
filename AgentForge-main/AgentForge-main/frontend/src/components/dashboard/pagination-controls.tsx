"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

const PAGE_SIZES = [10, 25, 50, 100];

export function PaginationControls({
  page,
  pageSize,
  totalCount,
  hasMore,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  totalCount: number;
  hasMore: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const start = totalCount === 0 ? 0 : page * pageSize + 1;
  const end = Math.min((page + 1) * pageSize, totalCount);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>Rows per page</span>
        <select
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          className="rounded-md border border-border/60 bg-background px-1.5 py-1 font-mono text-xs text-foreground"
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>

      <span className="tabular-nums">
        {start}–{end} of {totalCount}
      </span>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          className="size-7"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="size-3.5" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="size-7"
          disabled={!hasMore}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
