import type {
  AgentDetailOut,
  ApiErrorBody,
  CheckpointListOut,
  ConversationOut,
  DocumentationListResponse,
  FailureDetailOut,
  KnowledgeEntryOut,
  MCPConnectionStatus,
  MCPExecuteResult,
  MCPMetricsOut,
  MCPServerOut,
  MCPToolOut,
  ProjectAccepted,
  ProjectDetailOut,
  ProjectFileContent,
  ProjectFileList,
  ProjectListOut,
  ReliabilitySummaryOut,
  RepoFileRead,
  RepoFileWrite,
  RepoTreeResponse,
  RunAccepted,
  RunDetail,
  RunList,
  RunLogsOut,
  RunProjectOut,
  TimelineOut,
  TokenResponse,
  UserOut,
  WorkflowGraphOut,
} from "@/lib/types";
import { clearStoredToken, getStoredToken } from "@/lib/auth-storage";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  type: string;

  constructor(status: number, type: string, message: string) {
    super(message);
    this.status = status;
    this.type = type;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearStoredToken();
    }

    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      body?.error?.type ?? "UnknownError",
      body?.error?.message ?? `Request to ${path} failed with ${response.status}`,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function register(email: string, password: string): Promise<UserOut> {
  return request<UserOut>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getMe(): Promise<UserOut> {
  return request<UserOut>("/api/v1/auth/me");
}

export interface ListParams {
  status?: string[];
  q?: string;
  dateFrom?: string;
  dateTo?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

function buildListQuery(params: ListParams): string {
  const search = new URLSearchParams();
  for (const value of params.status ?? []) search.append("status_filter", value);
  if (params.q) search.set("q", params.q);
  if (params.dateFrom) search.set("date_from", params.dateFrom);
  if (params.dateTo) search.set("date_to", params.dateTo);
  if (params.sort) search.set("sort", params.sort);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function listRuns(params: ListParams = {}): Promise<RunList> {
  return request<RunList>(`/api/v1/runs${buildListQuery(params)}`);
}

export function getRun(runId: string): Promise<RunDetail> {
  return request<RunDetail>(`/api/v1/runs/${runId}`);
}

export function createRun(requestText: string): Promise<RunAccepted> {
  return request<RunAccepted>("/api/v1/runs", {
    method: "POST",
    body: JSON.stringify({ request: requestText }),
  });
}

export function resumeRun(runId: string): Promise<RunAccepted> {
  return request<RunAccepted>(`/api/v1/runs/${runId}/resume`, {
    method: "POST",
  });
}

export function getRunProject(runId: string): Promise<RunProjectOut> {
  return request<RunProjectOut>(`/api/v1/runs/${runId}/project`);
}

export function listKnowledge(runId: string): Promise<{ entries: KnowledgeEntryOut[] }> {
  return request<{ entries: KnowledgeEntryOut[] }>(`/api/v1/runs/${runId}/knowledge`);
}

export function getDocumentation(runId: string): Promise<DocumentationListResponse> {
  return request<DocumentationListResponse>(`/api/v1/runs/${runId}/repo/documentation`);
}

export async function downloadRepositoryZip(runId: string): Promise<{ blob: Blob; filename: string }> {
  const token = getStoredToken();

  const response = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/repo/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      body?.error?.type ?? "UnknownError",
      body?.error?.message ?? `Request to download the repository failed with ${response.status}`,
    );
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? `${runId}.zip`;
  const blob = await response.blob();

  return { blob, filename };
}


export function createProject(requestText: string): Promise<ProjectAccepted> {
  return request<ProjectAccepted>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({ request: requestText }),
  });
}

export function continueProject(projectId: string, message: string): Promise<ProjectAccepted> {
  return request<ProjectAccepted>(`/api/v1/projects/${projectId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function listProjects(params: ListParams = {}): Promise<ProjectListOut> {
  return request<ProjectListOut>(`/api/v1/projects${buildListQuery(params)}`);
}

export function getProjectDetail(projectId: string): Promise<ProjectDetailOut> {
  return request<ProjectDetailOut>(`/api/v1/projects/${projectId}`);
}

export function getProjectConversation(projectId: string): Promise<ConversationOut> {
  return request<ConversationOut>(`/api/v1/projects/${projectId}/conversation`);
}

export function renameProject(projectId: string, name: string): Promise<ProjectDetailOut> {
  return request<ProjectDetailOut>(`/api/v1/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/api/v1/projects/${projectId}`, { method: "DELETE" });
}

export function listFiles(runId: string): Promise<ProjectFileList> {
  return request<ProjectFileList>(`/api/v1/runs/${runId}/files`);
}

export function getFileContent(runId: string, path: string): Promise<ProjectFileContent> {
  return request<ProjectFileContent>(
    `/api/v1/runs/${runId}/files/${path.split("/").map(encodeURIComponent).join("/")}`,
  );
}

function encodeRepoPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function getRepoTree(runId: string): Promise<RepoTreeResponse> {
  return request<RepoTreeResponse>(`/api/v1/runs/${runId}/repo/tree`);
}

export function readRepoFile(runId: string, path: string): Promise<RepoFileRead> {
  return request<RepoFileRead>(`/api/v1/runs/${runId}/repo/files/${encodeRepoPath(path)}`);
}

export function saveRepoFile(
  runId: string,
  path: string,
  content: string,
  expectedVersion?: string,
): Promise<RepoFileWrite> {
  return request<RepoFileWrite>(`/api/v1/runs/${runId}/repo/files/${encodeRepoPath(path)}`, {
    method: "PUT",
    body: JSON.stringify({ content, expected_version: expectedVersion }),
  });
}


export function getFailureDetail(runId: string): Promise<FailureDetailOut> {
  return request<FailureDetailOut>(`/api/v1/runs/${runId}/failure`);
}

export function listCheckpoints(runId: string): Promise<CheckpointListOut> {
  return request<CheckpointListOut>(`/api/v1/runs/${runId}/checkpoints`);
}

export function getRunTimeline(runId: string): Promise<TimelineOut> {
  return request<TimelineOut>(`/api/v1/runs/${runId}/timeline`);
}

export function getRunLogs(runId: string): Promise<RunLogsOut> {
  return request<RunLogsOut>(`/api/v1/runs/${runId}/logs`);
}

export function retryFailedAgent(runId: string): Promise<RunAccepted> {
  return request<RunAccepted>(`/api/v1/runs/${runId}/retry-agent`, { method: "POST" });
}

export function restartFromCheckpoint(runId: string, checkpointId: string): Promise<RunAccepted> {
  return request<RunAccepted>(`/api/v1/runs/${runId}/restart-checkpoint`, {
    method: "POST",
    body: JSON.stringify({ checkpoint_id: checkpointId }),
  });
}

export function restartProjectWorkflow(projectId: string): Promise<ProjectAccepted> {
  return request<ProjectAccepted>(`/api/v1/projects/${projectId}/restart`, { method: "POST" });
}

export function duplicateProjectAndRetry(projectId: string): Promise<ProjectAccepted> {
  return request<ProjectAccepted>(`/api/v1/projects/${projectId}/duplicate`, { method: "POST" });
}


export function getReliabilitySummary(): Promise<ReliabilitySummaryOut> {
  return request<ReliabilitySummaryOut>(`/api/v1/reliability/summary`);
}

export function getAgentReliabilityDetail(agent: string): Promise<AgentDetailOut> {
  return request<AgentDetailOut>(`/api/v1/reliability/agents/${encodeURIComponent(agent)}`);
}


export function getWorkflowGraph(): Promise<WorkflowGraphOut> {
  return request<WorkflowGraphOut>(`/api/v1/workflow/graph`);
}

export function eventsStreamUrl(runId: string): string {
  const token = getStoredToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE_URL}/api/v1/runs/${runId}/events${query}`;
}

export function healthCheck(): Promise<{ status: string; database: string }> {
  return request(`/health`);
}

export function wakeBackend(): void {
  fetch(`${API_BASE_URL}/`).catch(() => {});
}

export function listMCPServers(): Promise<{ servers: MCPServerOut[] }> {
  return request(`/api/v1/mcp/servers`);
}

export function getMCPServer(serverId: string): Promise<MCPServerOut> {
  return request(`/api/v1/mcp/servers/${encodeURIComponent(serverId)}`);
}

export function listMCPTools(params: { server?: string; query?: string } = {}): Promise<{
  tools: MCPToolOut[];
}> {
  const search = new URLSearchParams();
  if (params.query) search.set("q", params.query);
  const path = params.server
    ? `/api/v1/mcp/servers/${encodeURIComponent(params.server)}/tools`
    : `/api/v1/mcp/tools`;
  const query = search.toString();
  return request(query ? `${path}?${query}` : path);
}

export function checkMCPServerHealth(serverId: string): Promise<{
  server_id: string;
  status: MCPConnectionStatus;
  checked_at: string;
  latency_ms: number | null;
  version: string | null;
  error: string | null;
}> {
  return request(`/api/v1/mcp/servers/${encodeURIComponent(serverId)}/health-check`, { method: "POST" });
}

export function refreshMCPRegistry(): Promise<{ refreshed_servers: string[] }> {
  return request(`/api/v1/mcp/refresh`, { method: "POST" });
}

export function reconnectMCPServer(serverId: string): Promise<{
  server_id: string;
  status: MCPConnectionStatus;
  checked_at: string;
  latency_ms: number | null;
  version: string | null;
  error: string | null;
}> {
  return request(`/api/v1/mcp/servers/${encodeURIComponent(serverId)}/reconnect`, { method: "POST" });
}

export function getMCPMetrics(): Promise<{ metrics: MCPMetricsOut[] }> {
  return request(`/api/v1/mcp/metrics`);
}

export function executeMCPTool(params: {
  tool_identity: string;
  arguments: Record<string, unknown>;
}): Promise<MCPExecuteResult> {
  return request(`/api/v1/mcp/execute`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}
