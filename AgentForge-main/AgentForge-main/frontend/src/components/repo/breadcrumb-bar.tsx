"use client";

import { ChevronRight } from "lucide-react";
import { getFileIcon } from "@/lib/file-icons";

export function BreadcrumbBar({
  path,
  onNavigate,
}: {
  path: string;
  onNavigate: (folderPath: string) => void;
}) {
  const segments = path.split("/").filter(Boolean);
  const fileName = segments[segments.length - 1];
  const { icon: Icon, color } = getFileIcon(fileName);

  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-border/60 bg-surface/40 px-3 py-1.5 text-xs text-muted-foreground">
      {segments.map((segment, index) => {
        const isLast = index === segments.length - 1;
        const folderPath = segments.slice(0, index + 1).join("/");

        return (
          <span key={folderPath} className="flex shrink-0 items-center gap-1">
            {index > 0 && <ChevronRight className="size-3 shrink-0 opacity-50" />}
            {isLast ? (
              <span className="flex items-center gap-1 text-foreground/80">
                <Icon className={`size-3.5 shrink-0 ${color}`} />
                {segment}
              </span>
            ) : (
              <button
                onClick={() => onNavigate(folderPath)}
                className="rounded px-1 py-0.5 hover:bg-accent/60 hover:text-foreground"
              >
                {segment}
              </button>
            )}
          </span>
        );
      })}
    </div>
  );
}
