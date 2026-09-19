"use client";

import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { ApiError, continueProject, getProjectConversation } from "@/lib/api";
import { useLiveStatusFromEvents } from "@/hooks/use-live-status";
import { useSharedRunEvents } from "@/hooks/use-run-events-context";
import { MessageList, type PendingMessage } from "@/components/chat/message-list";
import { Composer } from "@/components/chat/composer";
import { Skeleton } from "@/components/ui/skeleton";
import type { ProjectDetailOut } from "@/lib/types";

const ACTIVE_STATUSES = new Set(["initialized", "running", "waiting_for_user"]);

let clientIdCounter = 0;
function nextClientId(): string {
  clientIdCounter += 1;
  return `pending-${Date.now()}-${clientIdCounter}`;
}

export function ChatPanel({ projectId, project }: { projectId: string; project: ProjectDetailOut }) {
  const queryClient = useQueryClient();
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingMessage[]>([]);

  const conversationQuery = useQuery({
    queryKey: ["project-conversation", projectId],
    queryFn: () => getProjectConversation(projectId),
  });

  const activeRunId =
    pendingRunId ?? (ACTIVE_STATUSES.has(project.status) ? project.latest_run_id : null);

  const handleTerminal = useCallback(() => {
    setPendingRunId(null);
    queryClient
      .invalidateQueries({ queryKey: ["project-conversation", projectId] })
      .then(() => setPending([]));
    queryClient.invalidateQueries({ queryKey: ["project-detail", projectId] });

    if (project.latest_run_id) {
      queryClient.invalidateQueries({ queryKey: ["repo-tree", project.latest_run_id] });
    }
  }, [projectId, queryClient]);

  const { events } = useSharedRunEvents();
  const liveStatus = useLiveStatusFromEvents(events, handleTerminal) ?? (activeRunId ? "Starting…" : null);

  const continueMutation = useMutation({
    mutationFn: ({ content }: { clientId: string; content: string }) => continueProject(projectId, content),
    onSuccess: (result, variables) => {
      setPendingRunId(result.run_id);
      setPending((current) =>
        current.map((message) =>
          message.clientId === variables.clientId ? { ...message, status: "sent" } : message,
        ),
      );
      queryClient.invalidateQueries({ queryKey: ["project-detail", projectId] });
    },
    onError: (_error, variables) => {
      setPending((current) =>
        current.map((message) =>
          message.clientId === variables.clientId ? { ...message, status: "failed" } : message,
        ),
      );
    },
  });

  function sendMessage(content: string) {
    const clientId = nextClientId();
    setPending((current) => [...current, { clientId, content, status: "sending" }]);
    continueMutation.mutate({ clientId, content });
  }

  function retryMessage(clientId: string) {
    const message = pending.find((entry) => entry.clientId === clientId);
    if (!message) return;
    setPending((current) =>
      current.map((entry) => (entry.clientId === clientId ? { ...entry, status: "sending" } : entry)),
    );
    continueMutation.mutate({ clientId, content: message.content });
  }

  const isBusy = activeRunId !== null || continueMutation.isPending;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {conversationQuery.isLoading ? (
        <div className="space-y-3 p-4">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="ml-auto h-10 w-1/2" />
        </div>
      ) : conversationQuery.isError ? (
        <div className="flex h-full items-center justify-center gap-2 text-sm text-status-failed">
          <TriangleAlert className="size-4" />
          Couldn&apos;t load the conversation.
        </div>
      ) : (
        <MessageList
          messages={conversationQuery.data?.messages ?? []}
          pending={pending}
          onRetry={retryMessage}
          liveStatus={liveStatus}
        />
      )}

      <Composer
        disabled={isBusy}
        isSending={continueMutation.isPending}
        placeholder={
          isBusy
            ? "Waiting for the current run to finish…"
            : 'Ask for a change… (e.g. "Add authentication")'
        }
        onSend={sendMessage}
      />

      {continueMutation.isError && (
        <p className="border-t border-border/60 bg-status-failed/10 px-4 py-2 text-xs text-status-failed">
          {continueMutation.error instanceof ApiError
            ? continueMutation.error.message
            : "Couldn't send that message."}
        </p>
      )}
    </div>
  );
}
