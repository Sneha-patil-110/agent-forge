"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronsDownUp,
  Crosshair,
  FileArchive,
  FolderTree,
  History,
  RefreshCw,
  Search,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError, downloadRepositoryZip, getRepoTree, readRepoFile, saveRepoFile } from "@/lib/api";
import { fromRepoTree, ancestorFolders, flattenFiles } from "@/lib/file-tree";
import { getFileIcon, isMarkdown } from "@/lib/file-icons";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { cn } from "@/lib/utils";
import type { RepoFileRead, WorkflowEventPayload } from "@/lib/types";
import { BreadcrumbBar } from "@/components/repo/breadcrumb-bar";
import { FileTree } from "@/components/repo/file-tree";
import { TabBar } from "@/components/repo/tab-bar";
import { CodeEditor } from "@/components/repo/code-editor";
import { MarkdownPreview } from "@/components/repo/markdown-preview";
import { FileInspector } from "@/components/repo/file-inspector";
import { QuickOpen } from "@/components/repo/quick-open";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const FILES_TRIGGERING_EVENTS = new Set([
  "agent_completed",
  "workflow_completed",
  "testing_passed",
  "file_created",
  "file_modified",
  "file_deleted",
  "file_renamed",
  "folder_created",
  "folder_deleted",
]);

const MAX_RECENTLY_CLOSED = 10;

function moveInArray(list: string[], value: string, direction: "left" | "right"): string[] {
  const index = list.indexOf(value);
  const swapWith = direction === "left" ? index - 1 : index + 1;
  if (index === -1 || swapWith < 0 || swapWith >= list.length) return list;
  const next = [...list];
  [next[index], next[swapWith]] = [next[swapWith], next[index]];
  return next;
}

function moveUnpinnedTab(
  openPaths: string[],
  pinnedPaths: string[],
  path: string,
  direction: "left" | "right",
): string[] {
  const pinnedSet = new Set(pinnedPaths);
  const unpinnedIndices = openPaths
    .map((p, i) => (pinnedSet.has(p) ? -1 : i))
    .filter((i) => i !== -1);
  const reordered = moveInArray(
    unpinnedIndices.map((i) => openPaths[i]),
    path,
    direction,
  );
  const next = [...openPaths];
  unpinnedIndices.forEach((originalIndex, k) => {
    next[originalIndex] = reordered[k];
  });
  return next;
}

export function RepoExplorer({
  runId,
  events,
  storageKey,
}: {
  runId: string;
  events: WorkflowEventPayload[];
  storageKey?: string;
}) {
  const key = storageKey ?? runId;
  const queryClient = useQueryClient();
  const [quickOpenOpen, setQuickOpenOpen] = useState(false);

  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const [expandedList, setExpandedList] = usePersistedState<string[]>(
    `agentforge:expanded:${key}`,
    [],
  );
  const expanded = useMemo(() => new Set(expandedList), [expandedList]);

  const [openPaths, setOpenPaths] = usePersistedState<string[]>(
    `agentforge:tabs:${key}`,
    [],
  );
  const [activePath, setActivePath] = usePersistedState<string | null>(
    `agentforge:active-file:${key}`,
    null,
  );
  const [pinnedPaths, setPinnedPaths] = usePersistedState<string[]>(
    `agentforge:pinned:${key}`,
    [],
  );
  const [recentlyClosed, setRecentlyClosed] = usePersistedState<string[]>(
    `agentforge:recently-closed:${key}`,
    [],
  );

  const treeQuery = useQuery({
    queryKey: ["repo-tree", runId],
    queryFn: () => getRepoTree(runId),
  });

  const lastEventCount = useRef(events.length);
  useEffect(() => {
    if (events.length === lastEventCount.current) return;
    const newEvents = events.slice(lastEventCount.current);
    lastEventCount.current = events.length;

    if (newEvents.some((event) => FILES_TRIGGERING_EVENTS.has(event.event_type))) {
      queryClient.invalidateQueries({ queryKey: ["repo-tree", runId] });
    }
  }, [events, runId]);

  const tree = useMemo(() => fromRepoTree(treeQuery.data?.tree ?? []), [treeQuery.data]);
  const allFiles = useMemo(() => flattenFiles(tree), [tree]);

  const contentQuery = useQuery({
    queryKey: ["repo-file", runId, activePath],
    queryFn: () => readRepoFile(runId, activePath as string),
    enabled: activePath !== null,
    staleTime: 30_000,
  });

  const savedContent = contentQuery.data?.content ?? "";
  const draft = activePath !== null ? drafts[activePath] : undefined;
  const displayedContent = draft ?? savedContent;
  const isActiveDirty = activePath !== null && draft !== undefined && draft !== savedContent;

  function isPathDirty(path: string): boolean {
    const pathDraft = drafts[path];
    if (pathDraft === undefined) return false;
    const cached = queryClient.getQueryData<RepoFileRead>(["repo-file", runId, path]);
    return cached !== undefined && pathDraft !== cached.content;
  }

  const dirtyPaths = useMemo(
    () => new Set(Object.keys(drafts).filter((path) => isPathDirty(path))),
    [drafts, runId],
  );

  const saveMutation = useMutation({
    mutationFn: ({ path, content, version }: { path: string; content: string; version?: string }) =>
      saveRepoFile(runId, path, content, version),
    onSuccess: (result, variables) => {
      queryClient.setQueryData(["repo-file", runId, variables.path], {
        path: variables.path,
        content: variables.content,
        version: result.version,
      });
      setDrafts((current) => {
        const next = { ...current };
        delete next[variables.path];
        return next;
      });
    },
    onError: (error: Error, variables) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.error("Someone else changed this file", {
          description: `${variables.path} was modified since you last loaded it.`,
          action: {
            label: "Reload",
            onClick: () => {
              queryClient.invalidateQueries({ queryKey: ["repo-file", runId, variables.path] });
              setDrafts((current) => {
                const next = { ...current };
                delete next[variables.path];
                return next;
              });
            },
          },
        });
      } else {
        toast.error("Couldn't save", { description: error.message });
      }
    },
  });

  function handleSave() {
    if (!activePath) return;
    const pendingDraft = drafts[activePath];
    if (pendingDraft === undefined || pendingDraft === savedContent) return;
    saveMutation.mutate({ path: activePath, content: pendingDraft, version: contentQuery.data?.version });
  }

  function toggleFolder(path: string) {
    setExpandedList((current) =>
      current.includes(path) ? current.filter((p) => p !== path) : [...current, path],
    );
  }

  function openFile(path: string) {
    setOpenPaths((current) => (current.includes(path) ? current : [...current, path]));
    setActivePath(path);
  }

  function pushRecentlyClosed(path: string) {
    setRecentlyClosed((current) =>
      [path, ...current.filter((p) => p !== path)].slice(0, MAX_RECENTLY_CLOSED),
    );
  }

  function closeTab(path: string) {
    if (isPathDirty(path) && !window.confirm(`Discard unsaved changes to ${path}?`)) {
      return;
    }

    if (drafts[path] !== undefined) {
      setDrafts((current) => {
        const next = { ...current };
        delete next[path];
        return next;
      });
    }

    pushRecentlyClosed(path);
    setPinnedPaths((current) => current.filter((p) => p !== path));
    setOpenPaths((current) => {
      const next = current.filter((p) => p !== path);
      if (activePath === path) {
        setActivePath(next.length > 0 ? next[next.length - 1] : null);
      }
      return next;
    });
  }

  function handlePin(path: string) {
    setPinnedPaths((current) =>
      current.includes(path) ? current.filter((p) => p !== path) : [...current, path],
    );
  }

  function handleReorder(path: string, direction: "left" | "right") {
    if (pinnedPaths.includes(path)) {
      setPinnedPaths((current) => moveInArray(current, path, direction));
    } else {
      setOpenPaths((current) => moveUnpinnedTab(current, pinnedPaths, path, direction));
    }
  }

  async function handleDownload(path: string) {
    const filename = path.split("/").pop() ?? path;
    const pathDraft = drafts[path];
    let content: string;

    if (pathDraft !== undefined) {
      content = pathDraft;
    } else {
      const cached = queryClient.getQueryData<RepoFileRead>(["repo-file", runId, path]);

      if (cached) {
        content = cached.content;
      } else {
        try {
          content = (await readRepoFile(runId, path)).content;
        } catch (error) {
          toast.error("Couldn't download", {
            description: error instanceof ApiError ? error.message : "Unknown error",
          });
          return;
        }
      }
    }

    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function handleDownloadZip() {
    try {
      const { blob, filename } = await downloadRepositoryZip(runId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error("Couldn't download the repository", {
        description: error instanceof ApiError ? error.message : "Unknown error",
      });
    }
  }

  function closeOthers(path: string) {
    setOpenPaths((current) => Array.from(new Set([...pinnedPaths.filter((p) => current.includes(p)), path])));
    setActivePath(path);
  }

  function revealPath(path: string) {
    setExpandedList((current) => Array.from(new Set([...current, ...ancestorFolders(path), path])));
    requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>(`[data-path="${CSS.escape(path)}"]`)
        ?.scrollIntoView({ block: "center" });
    });
  }

  function revealActiveFile() {
    if (!activePath) return;
    revealPath(activePath);
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "p") {
        event.preventDefault();
        setQuickOpenOpen(true);
      } else if ((event.metaKey || event.ctrlKey) && event.key === "w" && activePath) {
        event.preventDefault();
        closeTab(activePath);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activePath]);

  return (
    <div className="grid h-full min-h-0 grid-cols-[16rem_1fr_16rem] grid-rows-[minmax(0,1fr)] overflow-hidden rounded-xl border border-border/60">
      <aside className="flex min-h-0 flex-col overflow-hidden border-r border-border/60 bg-surface/40">
        <div className="flex items-center justify-between border-b border-border/60 px-2 py-1.5">
          <span className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted-foreground">
            <FolderTree className="size-3.5" />
            Files
          </span>
          <div className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={() => setQuickOpenOpen(true)}
              title="Quick open"
              aria-label="Quick open"
            >
              <Search className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={revealActiveFile}
              title="Reveal active file"
              aria-label="Reveal active file in tree"
            >
              <Crosshair className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={() => setExpandedList([])}
              title="Collapse all folders"
              aria-label="Collapse all folders"
            >
              <ChevronsDownUp className="size-3.5" />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6"
                  disabled={recentlyClosed.length === 0}
                  title="Recently closed"
                  aria-label="Recently closed files"
                >
                  <History className="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>Recently closed</DropdownMenuLabel>
                {recentlyClosed.map((path) => {
                  const name = path.split("/").pop() ?? path;
                  const { icon: Icon, color } = getFileIcon(name);
                  return (
                    <DropdownMenuItem
                      key={path}
                      onSelect={() => {
                        openFile(path);
                        setRecentlyClosed((current) => current.filter((p) => p !== path));
                      }}
                    >
                      <Icon className={cn("size-3.5", color)} />
                      <span className="truncate">{name}</span>
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={() => queryClient.invalidateQueries({ queryKey: ["repo-tree", runId] })}
              title="Refresh file list"
              aria-label="Refresh file list"
            >
              <RefreshCw className={cnRefreshing(treeQuery.isFetching)} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              onClick={handleDownloadZip}
              title="Download repository as ZIP"
              aria-label="Download repository as ZIP"
            >
              <FileArchive className="size-3.5" />
            </Button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {treeQuery.isLoading ? (
            <div className="space-y-2 p-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : treeQuery.isError ? (
            <div className="flex items-start gap-2 p-3 text-xs text-status-failed">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              Couldn&apos;t load the file list.
            </div>
          ) : (
            <FileTree
              tree={tree}
              expandedPaths={expanded}
              selectedPath={activePath}
              onToggle={toggleFolder}
              onSelect={(node) => openFile(node.path)}
            />
          )}
        </div>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col">
        <TabBar
          openPaths={openPaths}
          pinnedPaths={pinnedPaths}
          activePath={activePath}
          dirtyPaths={dirtyPaths}
          onActivate={setActivePath}
          onClose={closeTab}
          onCloseOthers={closeOthers}
          onDownload={handleDownload}
          onPin={handlePin}
          onReorder={handleReorder}
          onCloseAll={() => {
            const closablePaths = openPaths.filter((path) => !pinnedPaths.includes(path));
            const dirtyOpenPaths = closablePaths.filter((path) => isPathDirty(path));
            if (dirtyOpenPaths.length > 0 && !window.confirm("Discard unsaved changes in all open tabs?")) {
              return;
            }
            closablePaths.forEach(pushRecentlyClosed);
            setDrafts((current) => {
              const next = { ...current };
              closablePaths.forEach((path) => delete next[path]);
              return next;
            });
            const stillOpenPinned = openPaths.filter((path) => pinnedPaths.includes(path));
            setOpenPaths(stillOpenPinned);
            setActivePath(stillOpenPinned.length > 0 ? stillOpenPinned[0] : null);
          }}
        />
        {activePath && <BreadcrumbBar path={activePath} onNavigate={revealPath} />}
        <div className="min-h-0 flex-1">
          {!activePath ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <FolderTree className="size-6 opacity-50" />
              Select a file, or press {"⌘"}/Ctrl+P to search
            </div>
          ) : contentQuery.isLoading ? (
            <Skeleton className="h-full w-full rounded-none" />
          ) : contentQuery.isError ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-status-failed">
              <TriangleAlert className="size-4" />
              Couldn&apos;t load this file.
            </div>
          ) : isMarkdown(activePath) ? (
            <MarkdownPreview
              path={activePath}
              content={displayedContent}
              isDirty={isActiveDirty}
              isSaving={saveMutation.isPending && saveMutation.variables?.path === activePath}
              onChange={(value) => setDrafts((current) => ({ ...current, [activePath]: value }))}
              onSave={handleSave}
            />
          ) : (
            <CodeEditor
              path={activePath}
              content={displayedContent}
              isDirty={isActiveDirty}
              isSaving={saveMutation.isPending && saveMutation.variables?.path === activePath}
              onDownload={handleDownload}
              onChange={(value) => setDrafts((current) => ({ ...current, [activePath]: value }))}
              onSave={handleSave}
            />
          )}
        </div>
      </section>

      <aside className="min-h-0 overflow-hidden border-l border-border/60 bg-surface/40">
        <FileInspector runId={runId} path={activePath} />
      </aside>

      <QuickOpen
        runId={runId}
        open={quickOpenOpen}
        onOpenChange={setQuickOpenOpen}
        files={allFiles}
        activePath={activePath}
        activeContent={displayedContent}
        onSelect={openFile}
      />
    </div>
  );
}

function cnRefreshing(isFetching: boolean) {
  return isFetching ? "size-3.5 animate-spin" : "size-3.5";
}
