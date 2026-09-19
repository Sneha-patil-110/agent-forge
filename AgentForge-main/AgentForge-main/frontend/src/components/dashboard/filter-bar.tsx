"use client";

import { useEffect, useRef } from "react";
import { ArrowUpDown, Filter, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SORT_OPTIONS, STATUS_FILTER_OPTIONS, type SortOption, type StatusFilterValue } from "@/lib/types";

export interface FilterState {
  status: StatusFilterValue[];
  q: string;
  dateFrom: string;
  dateTo: string;
  sort: SortOption;
}

export function FilterBar({
  filters,
  onChange,
}: {
  filters: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isTyping =
        target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;

      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  function toggleStatus(value: StatusFilterValue) {
    const next = filters.status.includes(value)
      ? filters.status.filter((s) => s !== value)
      : [...filters.status, value];
    onChange({ ...filters, status: next });
  }

  const activeFilterCount = filters.status.length + (filters.dateFrom || filters.dateTo ? 1 : 0);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-56 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={searchRef}
          value={filters.q}
          onChange={(event) => onChange({ ...filters, q: event.target.value })}
          placeholder="Search by run ID, project name, or prompt…"
          aria-label="Search projects"
          className="h-9 pl-8 text-sm pr-8"
        />
        {filters.q ? (
          <button
            onClick={() => onChange({ ...filters, q: "" })}
            aria-label="Clear search"
            className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        ) : (
          <kbd className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 rounded border border-border/60 bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            /
          </kbd>
        )}
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <Filter className="size-3.5" />
            Status
            {activeFilterCount > 0 && (
              <span className="rounded-full bg-primary/20 px-1.5 text-[10px] text-primary">
                {activeFilterCount}
              </span>
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Status</DropdownMenuLabel>
          {STATUS_FILTER_OPTIONS.map((option) => (
            <DropdownMenuCheckboxItem
              key={option.value}
              checked={filters.status.includes(option.value)}
              onCheckedChange={() => toggleStatus(option.value)}
              onSelect={(event) => event.preventDefault()}
            >
              {option.label}
            </DropdownMenuCheckboxItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-[10px] font-normal text-muted-foreground/70">
            Date range
          </DropdownMenuLabel>
          <div className="flex items-center gap-1.5 px-2 py-1.5">
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(event) => onChange({ ...filters, dateFrom: event.target.value })}
              aria-label="From date"
              className="w-full rounded-md border border-border/60 bg-background px-1.5 py-1 text-xs text-foreground"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={filters.dateTo}
              onChange={(event) => onChange({ ...filters, dateTo: event.target.value })}
              aria-label="To date"
              className="w-full rounded-md border border-border/60 bg-background px-1.5 py-1 text-xs text-foreground"
            />
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <ArrowUpDown className="size-3.5" />
            {SORT_OPTIONS.find((option) => option.value === filters.sort)?.label ?? "Sort"}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-48">
          <DropdownMenuRadioGroup
            value={filters.sort}
            onValueChange={(value) => onChange({ ...filters, sort: value as SortOption })}
          >
            {SORT_OPTIONS.map((option) => (
              <DropdownMenuRadioItem key={option.value} value={option.value}>
                {option.label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {(filters.status.length > 0 || filters.q || filters.dateFrom || filters.dateTo) && (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() =>
            onChange({ status: [], q: "", dateFrom: "", dateTo: "", sort: filters.sort })
          }
        >
          Clear
        </Button>
      )}
    </div>
  );
}
