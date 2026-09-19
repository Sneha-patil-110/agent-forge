import { McpDashboard } from "@/components/mcp/mcp-dashboard";

export default function McpPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">MCP Servers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Inspect configured MCP servers, their health, and the tools they expose.
        </p>
      </div>
      <McpDashboard />
    </div>
  );
}
