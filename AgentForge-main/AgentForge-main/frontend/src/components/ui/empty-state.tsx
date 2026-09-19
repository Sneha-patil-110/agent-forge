import type { ElementType, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  className,
}: {
  icon: ElementType;
  title: string;
  description?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "surface-card flex flex-col items-center gap-2 rounded-xl px-4 py-10 text-center text-muted-foreground",
        className,
      )}
    >
      <Icon className="size-5" />
      <p className="text-sm">{title}</p>
      {description && <div className="text-xs">{description}</div>}
    </div>
  );
}
