"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Inbox, TriangleAlert } from "lucide-react";
import { ApiError, API_BASE_URL, listProjects } from "@/lib/api";
import { ProjectCard } from "@/components/dashboard/project-card";
import { FilterBar, type FilterState } from "@/components/dashboard/filter-bar";
import { PaginationControls } from "@/components/dashboard/pagination-controls";
import { Skeleton } from "@/components/ui/skeleton";

const DEFAULT_FILTERS: FilterState = {
  status: [],
  q: "",
  dateFrom: "",
  dateTo: "",
  sort: "recently_updated",
};

export function ProjectTable() {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  function updateFilters(next: FilterState) {
    setFilters(next);
    setPage(0);
  }

  function updatePageSize(size: number) {
    setPageSize(size);
    setPage(0);
  }

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["projects", { ...filters, page, pageSize }],
    queryFn: () =>
      listProjects({
        status: filters.status,
        q: filters.q || undefined,
        dateFrom: filters.dateFrom || undefined,
        dateTo: filters.dateTo || undefined,
        sort: filters.sort,
        limit: pageSize,
        offset: page * pageSize,
      }),
  });

  return (
    <div className="space-y-4">
      <FilterBar filters={filters} onChange={updateFilters} />

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} className="h-[62px] w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <div className="surface-card flex items-start gap-3 rounded-xl px-4 py-4 text-sm text-muted-foreground">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-status-failed" />
          <div>
            <p className="font-medium text-foreground">Couldn&apos;t load projects</p>
            <p className="mt-0.5">
              {error instanceof ApiError
                ? error.message
                : `Couldn't reach the AgentForge API at ${API_BASE_URL}. Is the backend running?`}
            </p>
          </div>
        </div>
      ) : (data?.projects.length ?? 0) === 0 ? (
        <div className="surface-card flex flex-col items-center gap-2 rounded-xl px-4 py-10 text-center text-muted-foreground">
          <Inbox className="size-5" />
          <p className="text-sm">
            {filters.q || filters.status.length > 0
              ? "No projects match these filters."
              : "No projects yet. Describe something above to get started."}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {data!.projects.map((project, index) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: index * 0.03 }}
            >
              <ProjectCard project={project} />
            </motion.div>
          ))}
        </div>
      )}

      {data && data.total_count > 0 && (
        <PaginationControls
          page={page}
          pageSize={pageSize}
          totalCount={data.total_count}
          hasMore={data.has_more}
          onPageChange={setPage}
          onPageSizeChange={updatePageSize}
        />
      )}
    </div>
  );
}
