"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { RotateCcw, TriangleAlert } from "lucide-react";
import { listProjects } from "@/lib/api";
import { ProjectCard } from "@/components/dashboard/project-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { StatusFilterValue } from "@/lib/types";

export function ProjectGroupSection({
  title,
  icon: Icon,
  status,
  sort = "recently_updated",
  accent = false,
}: {
  title: string;
  icon: React.ElementType;
  status: StatusFilterValue;
  sort?: "recently_updated" | "newest";
  accent?: boolean;
}) {
  const query = useQuery({
    queryKey: ["dashboard-projects", status],
    queryFn: () => listProjects({ status: [status], sort, limit: 5 }),
    refetchInterval: 4000,
  });

  const projects = query.data?.projects ?? [];

  if (query.isLoading) {
    return (
      <section className="mx-auto w-full max-w-2xl">
        <Skeleton className="mb-3 h-4 w-32" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="mx-auto w-full max-w-2xl">
        <div className="flex items-center gap-2 rounded-xl border border-border/60 p-4 text-sm text-muted-foreground">
          <TriangleAlert className="size-4 shrink-0 text-status-failed" />
          <span className="flex-1">Couldn&apos;t reach the backend. It may still be starting up.</span>
          <Button variant="outline" size="xs" className="gap-1" onClick={() => query.refetch()}>
            <RotateCcw className="size-3" />
            Retry
          </Button>
        </div>
      </section>
    );
  }

  if (projects.length === 0) return null;

  return (
    <section className="mx-auto w-full max-w-2xl">
      <h2 className="mb-3 flex items-center gap-1.5 font-mono text-xs font-medium tracking-wide text-muted-foreground uppercase">
        <Icon className={accent ? "size-3.5 text-primary" : "size-3.5"} />
        {title}
      </h2>
      <div className="space-y-2">
        {projects.map((project, index) => (
          <motion.div
            key={project.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: index * 0.03 }}
            className={accent ? "glow-ember rounded-xl" : undefined}
          >
            <ProjectCard project={project} />
          </motion.div>
        ))}
      </div>
    </section>
  );
}
