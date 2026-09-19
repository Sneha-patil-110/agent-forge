"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  Activity,
  KeyRound,
  Loader2,
  Plug,
  Radio,
  RefreshCw,
  Server,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { checkMCPServerHealth, reconnectMCPServer } from "@/lib/api";
import type { MCPConnectionStatus, MCPMetricsOut, MCPServerOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const STATUS_CONFIG: Record<MCPConnectionStatus, { label: string; className: string }> = {
  online: { label: "Online", className: "text-status-completed" },
  offline: { label: "Offline", className: "text-muted-foreground" },
  unreachable: { label: "Unreachable", className: "text-status-failed" },
  authentication_failed: { label: "Auth failed", className: "text-status-failed" },
  timeout: { label: "Timeout", className: "text-status-failed" },
  disabled: { label: "Disabled", className: "text-muted-foreground" },
};

export function McpServerCard({ server, metrics }: { server: MCPServerOut; metrics?: MCPMetricsOut }) {
  const queryClient = useQueryClient();
  const status = STATUS_CONFIG[server.connection_status];

  const invalidateServers = () => {
    queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
    queryClient.invalidateQueries({ queryKey: ["mcp-metrics"] });
  };

  const healthCheck = useMutation({
    mutationFn: () => checkMCPServerHealth(server.id),
    onSuccess: (result) => {
      invalidateServers();
      if (result.status !== "online") {
        toast.error(`${server.display_name} is ${STATUS_CONFIG[result.status].label.toLowerCase()}`, {
          description: result.error ?? undefined,
        });
      } else {
        toast.success(`${server.display_name} is online`);
      }
    },
    onError: (error: Error) => {
      toast.error("Health check failed", { description: error.message });
    },
  });

  const reconnect = useMutation({
    mutationFn: () => reconnectMCPServer(server.id),
    onSuccess: (result) => {
      invalidateServers();
      if (result.status !== "online") {
        toast.error(`${server.display_name} still ${STATUS_CONFIG[result.status].label.toLowerCase()} after reconnect`, {
          description: result.error ?? undefined,
        });
      } else {
        toast.success(`${server.display_name} reconnected`);
      }
    },
    onError: (error: Error) => {
      toast.error("Reconnect failed", { description: error.message });
    },
  });

  return (
    <div className="surface-card space-y-3 rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Server className="size-4" />
          </span>
          <div>
            <p className="text-sm font-medium text-foreground">{server.display_name}</p>
            <p className="font-mono text-xs text-muted-foreground">{server.id}</p>
          </div>
        </div>
        <span className={cn("flex items-center gap-1.5 text-xs font-medium", status.className)}>
          <Radio className="size-3" />
          {status.label}
        </span>
      </div>

      {server.description && <p className="text-xs text-muted-foreground">{server.description}</p>}

      <dl className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <Activity className="size-3.5" />
            Transport
          </dt>
          <dd className="text-foreground">
            {server.transport} {server.is_remote && "(remote)"}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <Wrench className="size-3.5" />
            Tools
          </dt>
          <dd className="text-foreground">{server.tool_count}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <KeyRound className="size-3.5" />
            Auth
          </dt>
          <dd className="text-foreground">
            {server.auth_type === "none" ? (
              "None"
            ) : (
              <Badge variant={server.auth_configured ? "secondary" : "destructive"} className="capitalize">
                {server.auth_type.replace("_", " ")}
                {!server.auth_configured && " (missing credential)"}
              </Badge>
            )}
          </dd>
        </div>
        {server.version && (
          <div className="flex items-center justify-between">
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <ShieldCheck className="size-3.5" />
              Version
            </dt>
            <dd className="text-foreground">{server.version}</dd>
          </div>
        )}
        {server.latency_ms !== null && (
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Latency</dt>
            <dd className="text-foreground">{server.latency_ms.toFixed(0)}ms</dd>
          </div>
        )}
        {metrics && metrics.total_executions > 0 && (
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">Executions</dt>
            <dd className="text-foreground">
              {metrics.total_executions}
              {metrics.total_failures > 0 && (
                <span className="text-status-failed"> ({metrics.total_failures} failed)</span>
              )}
              {metrics.active_requests > 0 && (
                <span className="text-muted-foreground"> · {metrics.active_requests} active</span>
              )}
            </dd>
          </div>
        )}
      </dl>

      <div className="flex items-center justify-between border-t border-border/60 pt-3">
        <span className="text-xs text-muted-foreground/70">
          {server.last_health_check
            ? `Checked ${formatDistanceToNow(new Date(server.last_health_check), { addSuffix: true })}`
            : "Never checked"}
        </span>
        <div className="flex items-center gap-1.5">
          <Button
            size="xs"
            variant="outline"
            disabled={reconnect.isPending}
            onClick={() => reconnect.mutate()}
            className="gap-1.5"
          >
            {reconnect.isPending ? <Loader2 className="size-3 animate-spin" /> : <Plug className="size-3" />}
            Reconnect
          </Button>
          <Button
            size="xs"
            variant="outline"
            disabled={healthCheck.isPending}
            onClick={() => healthCheck.mutate()}
            className="gap-1.5"
          >
            {healthCheck.isPending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <RefreshCw className="size-3" />
            )}
            Test
          </Button>
        </div>
      </div>
    </div>
  );
}
