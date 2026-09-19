"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, ServerOff, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { getMCPMetrics, listMCPServers, refreshMCPRegistry } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { McpServerCard } from "@/components/mcp/mcp-server-card";
import { McpToolExplorer } from "@/components/mcp/mcp-tool-explorer";

const UNSETTLED_STATUSES = new Set(["disabled"]);

export function McpDashboard() {
  const queryClient = useQueryClient();

  const serversQuery = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: () => listMCPServers(),
    refetchInterval: (query) => {
      const servers = query.state.data?.servers ?? [];
      const anyUnsettled = servers.some(
        (server) => server.last_health_check === null || UNSETTLED_STATUSES.has(server.connection_status)
      );
      return anyUnsettled ? 10000 : 30000;
    },
  });

  const metricsQuery = useQuery({
    queryKey: ["mcp-metrics"],
    queryFn: () => getMCPMetrics(),
    refetchInterval: 15000,
  });

  const metricsByServer = new Map(
    (metricsQuery.data?.metrics ?? []).map((entry) => [entry.server_name, entry])
  );

  const refresh = useMutation({
    mutationFn: () => refreshMCPRegistry(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
      queryClient.invalidateQueries({ queryKey: ["mcp-tools"] });
      if (result.refreshed_servers.length === 0) {
        toast.info("Nothing refreshed", { description: "No enabled servers could be reached." });
      } else {
        toast.success("Registry refreshed", { description: result.refreshed_servers.join(", ") });
      }
    },
    onError: (error: Error) => {
      toast.error("Refresh failed", { description: error.message });
    },
  });

  const servers = serversQuery.data?.servers ?? [];

  return (
    <div className="flex flex-col gap-8">
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Servers</h2>
          <Button
            size="sm"
            variant="outline"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
            className="gap-1.5"
          >
            {refresh.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            Refresh registry
          </Button>
        </div>

        {serversQuery.isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-44 w-full rounded-xl" />
            ))}
          </div>
        ) : serversQuery.isError ? (
          <div className="surface-card flex items-start gap-3 rounded-xl px-4 py-4 text-sm text-muted-foreground">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-status-failed" />
            Couldn&apos;t load MCP servers.
          </div>
        ) : servers.length === 0 ? (
          <div className="surface-card flex flex-col items-center gap-2 rounded-xl px-4 py-10 text-center text-muted-foreground">
            <ServerOff className="size-5" />
            <p className="text-sm">No MCP servers configured.</p>
            <p className="text-xs">
              Add one to <code className="font-mono">backend/mcp/config/mcp_servers.yaml</code>.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {servers.map((server) => (
              <McpServerCard key={server.id} server={server} metrics={metricsByServer.get(server.id)} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Tool explorer</h2>
        <McpToolExplorer />
      </section>
    </div>
  );
}
