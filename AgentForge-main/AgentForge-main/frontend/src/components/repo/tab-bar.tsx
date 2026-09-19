"use client";

import { motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Pin, PinOff, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { getFileIcon } from "@/lib/file-icons";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";

function Tab({
  path,
  isActive,
  isDirty,
  isPinned,
  canMoveLeft,
  canMoveRight,
  onActivate,
  onClose,
  onCloseOthers,
  onCloseAll,
  onDownload,
  onPin,
  onMove,
}: {
  path: string;
  isActive: boolean;
  isDirty: boolean;
  isPinned: boolean;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onCloseOthers: (path: string) => void;
  onCloseAll: () => void;
  onDownload: (path: string) => void;
  onPin: (path: string) => void;
  onMove: (path: string, direction: "left" | "right") => void;
}) {
  const name = path.split("/").pop() ?? path;
  const { icon: Icon, color } = getFileIcon(name);

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <motion.div
          layout
          role="tab"
          aria-selected={isActive}
          tabIndex={0}
          onClick={() => onActivate(path)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onActivate(path);
            }
          }}
          title={path}
          className={cn(
            "group relative flex shrink-0 cursor-default items-center gap-1.5 border-r border-border/50 px-3 py-2 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            isActive
              ? "bg-background text-foreground"
              : "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
            isPinned && "bg-surface-2/40",
          )}
        >
          {isPinned && <Pin className="size-3 shrink-0 text-primary" />}
          <Icon className={cn("size-3.5 shrink-0", color)} />
          {!isPinned && <span className="max-w-40 truncate">{name}</span>}
          {isDirty && (
            <span className="size-1.5 shrink-0 rounded-full bg-primary" title="Unsaved changes" />
          )}
          {!isPinned && (
            <button
              type="button"
              aria-label={`Close ${name}`}
              onClick={(event) => {
                event.stopPropagation();
                onClose(path);
              }}
              className="rounded p-0.5 opacity-0 hover:bg-accent focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 group-hover:opacity-100"
            >
              <X className="size-3" />
            </button>
          )}
          {isActive && (
            <motion.div
              layoutId="active-tab-indicator"
              className="absolute inset-x-0 -bottom-px h-0.5 bg-primary"
            />
          )}
        </motion.div>
      </ContextMenuTrigger>
      <ContextMenuContent className="w-48">
        <ContextMenuItem onSelect={() => onPin(path)}>
          {isPinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
          {isPinned ? "Unpin" : "Pin"}
        </ContextMenuItem>
        <ContextMenuItem disabled={!canMoveLeft} onSelect={() => onMove(path, "left")}>
          <ArrowLeft className="size-3.5" />
          Move left
        </ContextMenuItem>
        <ContextMenuItem disabled={!canMoveRight} onSelect={() => onMove(path, "right")}>
          <ArrowRight className="size-3.5" />
          Move right
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem onSelect={() => onDownload(path)}>Download</ContextMenuItem>
        {!isPinned && (
          <>
            <ContextMenuItem onSelect={() => onClose(path)}>Close</ContextMenuItem>
            <ContextMenuItem onSelect={() => onCloseOthers(path)}>Close others</ContextMenuItem>
            <ContextMenuItem onSelect={onCloseAll}>Close all</ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  );
}

export function TabBar({
  openPaths,
  pinnedPaths,
  activePath,
  dirtyPaths,
  onActivate,
  onClose,
  onCloseOthers,
  onCloseAll,
  onDownload,
  onPin,
  onReorder,
}: {
  openPaths: string[];
  pinnedPaths: string[];
  activePath: string | null;
  dirtyPaths: ReadonlySet<string>;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onCloseOthers: (path: string) => void;
  onCloseAll: () => void;
  onDownload: (path: string) => void;
  onPin: (path: string) => void;
  onReorder: (path: string, direction: "left" | "right") => void;
}) {
  if (openPaths.length === 0) return null;

  const pinnedSet = new Set(pinnedPaths);
  const pinned = pinnedPaths.filter((path) => openPaths.includes(path));
  const unpinned = openPaths.filter((path) => !pinnedSet.has(path));

  return (
    <div className="flex items-center overflow-x-auto border-b border-border/60 bg-surface/40">
      {pinned.map((path, index) => (
        <Tab
          key={path}
          path={path}
          isActive={path === activePath}
          isDirty={dirtyPaths.has(path)}
          isPinned
          canMoveLeft={index > 0}
          canMoveRight={index < pinned.length - 1}
          onActivate={onActivate}
          onClose={onClose}
          onCloseOthers={onCloseOthers}
          onCloseAll={onCloseAll}
          onDownload={onDownload}
          onPin={onPin}
          onMove={onReorder}
        />
      ))}
      {pinned.length > 0 && unpinned.length > 0 && (
        <span className="h-4 w-px shrink-0 self-center bg-border/60" />
      )}
      {unpinned.map((path, index) => (
        <Tab
          key={path}
          path={path}
          isActive={path === activePath}
          isDirty={dirtyPaths.has(path)}
          isPinned={false}
          canMoveLeft={index > 0}
          canMoveRight={index < unpinned.length - 1}
          onActivate={onActivate}
          onClose={onClose}
          onCloseOthers={onCloseOthers}
          onCloseAll={onCloseAll}
          onDownload={onDownload}
          onPin={onPin}
          onMove={onReorder}
        />
      ))}
    </div>
  );
}
