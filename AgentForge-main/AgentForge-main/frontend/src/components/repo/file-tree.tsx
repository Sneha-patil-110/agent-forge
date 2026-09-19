"use client";

import { useCallback, useMemo, useRef } from "react";
import { motion } from "framer-motion";
import { ChevronRight, Copy, FilePlus, FolderOpen, FolderPlus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { flattenVisible, type VisibleNode } from "@/lib/file-tree";
import { getFileIcon } from "@/lib/file-icons";
import type { FileTreeNode } from "@/lib/types";
import { EmptyState } from "@/components/ui/empty-state";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";

function NotSupportedItem({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <ContextMenuItem
      disabled
      className="text-muted-foreground"
      onSelect={(event) => event.preventDefault()}
    >
      <Icon className="size-3.5" />
      {label}
      <span className="ml-auto text-[10px] text-muted-foreground/70">Read-only</span>
    </ContextMenuItem>
  );
}

function FolderIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5 shrink-0 text-primary/80" fill="currentColor">
      {expanded ? (
        <path d="M1.5 2.5A1.5 1.5 0 0 1 3 1h3.586a1.5 1.5 0 0 1 1.06.44l1.415 1.414A1.5 1.5 0 0 0 10.12 3.5H13a1.5 1.5 0 0 1 1.5 1.5v.5h-11a1 1 0 0 0-.97.757L1.06 10.5a.5.5 0 0 1-.06-.24V2.5Zm-.44 8.55L2.06 6.76A1.5 1.5 0 0 1 3.5 5.6H14a1.5 1.5 0 0 1 1.45 1.86l-1.1 4.4A1.5 1.5 0 0 1 12.9 13H2.5a1.5 1.5 0 0 1-1.44-1.95Z" />
      ) : (
        <path d="M1.5 3A1.5 1.5 0 0 1 3 1.5h3.586a1.5 1.5 0 0 1 1.06.44l1.415 1.415a.5.5 0 0 0 .353.145H13A1.5 1.5 0 0 1 14.5 5v6.5A1.5 1.5 0 0 1 13 13H3a1.5 1.5 0 0 1-1.5-1.5V3Z" />
      )}
    </svg>
  );
}

export function FileTree({
  tree,
  expandedPaths,
  selectedPath,
  onToggle,
  onSelect,
}: {
  tree: FileTreeNode[];
  expandedPaths: Set<string>;
  selectedPath: string | null;
  onToggle: (path: string) => void;
  onSelect: (node: FileTreeNode) => void;
}) {
  const visible = useMemo(() => flattenVisible(tree, expandedPaths), [tree, expandedPaths]);
  const containerRef = useRef<HTMLDivElement>(null);

  const activate = useCallback(
    (item: VisibleNode) => {
      if (item.node.type === "folder") {
        onToggle(item.node.path);
      } else {
        onSelect(item.node);
      }
    },
    [onToggle, onSelect],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      const currentIndex = visible.findIndex(
        (item) => item.node.path === (document.activeElement as HTMLElement)?.dataset.path,
      );

      if (event.key === "ArrowDown") {
        event.preventDefault();
        const next = visible[Math.min(currentIndex + 1, visible.length - 1)];
        containerRef.current
          ?.querySelector<HTMLElement>(`[data-path="${CSS.escape(next?.node.path ?? "")}"]`)
          ?.focus();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        const prev = visible[Math.max(currentIndex - 1, 0)];
        containerRef.current
          ?.querySelector<HTMLElement>(`[data-path="${CSS.escape(prev?.node.path ?? "")}"]`)
          ?.focus();
      } else if (event.key === "ArrowRight") {
        const item = visible[currentIndex];
        if (item?.node.type === "folder" && !expandedPaths.has(item.node.path)) {
          event.preventDefault();
          onToggle(item.node.path);
        }
      } else if (event.key === "ArrowLeft") {
        const item = visible[currentIndex];
        if (item?.node.type === "folder" && expandedPaths.has(item.node.path)) {
          event.preventDefault();
          onToggle(item.node.path);
        }
      } else if (event.key === "Enter") {
        event.preventDefault();
        const item = visible[currentIndex];
        if (item) activate(item);
      }
    },
    [visible, expandedPaths, onToggle, activate],
  );

  if (tree.length === 0) {
    return <EmptyState icon={FolderOpen} title="No files yet" className="py-6" />;
  }

  return (
    <div ref={containerRef} role="tree" onKeyDown={handleKeyDown} className="py-1">
      {visible.map(({ node, depth }) => {
        const isSelected = node.type === "file" && node.path === selectedPath;
        const isExpanded = node.type === "folder" && expandedPaths.has(node.path);
        const { icon: Icon, color } = node.type === "file" ? getFileIcon(node.name) : { icon: null, color: "" };

        return (
          <ContextMenu key={node.path}>
            <ContextMenuTrigger asChild>
              <motion.div
                layout="position"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.12 }}
                role="treeitem"
                tabIndex={0}
                data-path={node.path}
                aria-selected={isSelected}
                aria-expanded={node.type === "folder" ? isExpanded : undefined}
                onClick={() => activate({ node, depth })}
                style={{ paddingLeft: `${depth * 14 + 8}px` }}
                className={cn(
                  "group flex cursor-pointer items-center gap-1.5 rounded-md py-1 pr-2 text-sm outline-none",
                  "hover:bg-accent/60 focus-visible:ring-1 focus-visible:ring-ring",
                  isSelected && "bg-primary/15 text-foreground",
                )}
              >
                {node.type === "folder" ? (
                  <>
                    <ChevronRight
                      className={cn(
                        "size-3 shrink-0 text-muted-foreground transition-transform",
                        isExpanded && "rotate-90",
                      )}
                    />
                    <FolderIcon expanded={isExpanded} />
                  </>
                ) : (
                  <>
                    <span className="size-3 shrink-0" />
                    {Icon && <Icon className={cn("size-3.5 shrink-0", color)} />}
                  </>
                )}
                <span className={cn("truncate", node.type === "folder" && "font-medium")}>
                  {node.name}
                </span>
              </motion.div>
            </ContextMenuTrigger>
            <ContextMenuContent className="w-52">
              <ContextMenuItem
                onSelect={() => {
                  navigator.clipboard.writeText(node.path);
                  toast.success("Path copied", { description: node.path });
                }}
              >
                <Copy className="size-3.5" />
                Copy path
              </ContextMenuItem>
              <ContextMenuSeparator />
              <NotSupportedItem icon={FilePlus} label="New file" />
              <NotSupportedItem icon={FolderPlus} label="New folder" />
              <NotSupportedItem icon={Pencil} label="Rename" />
              <NotSupportedItem icon={Trash2} label="Delete" />
            </ContextMenuContent>
          </ContextMenu>
        );
      })}
    </div>
  );
}
