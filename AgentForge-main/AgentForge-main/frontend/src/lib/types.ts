export type WorkflowStatus =
  | "initialized"
  | "running"
  | "waiting_for_user"
  | "completed"
  | "completed_with_verification_issues"
  | "failed";

export type AgentType =
  | "analysis"
  | "planner"
  | "architect"
  | "developer"
  | "static_validation"
  | "tester"
  | "debugger"
  | "reviewer"
  | "documentation";

export const FALLBACK_AGENT_PIPELINE: AgentType[] = [
  "analysis",
  "planner",
  "architect",
  "developer",
  "static_validation",
  "tester",
  "debugger",
  "reviewer",
  "documentation",
];

export interface RunSummary {
  run_id: string;
  project_id: string | null;
  status: WorkflowStatus;
  current_step: string | null;
  current_agent: AgentType | null;
  error_message: string | null;
  test_retry_count: number;
  review_retry_count: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface TestFailureSummary {
  name: string;
  message: string | null;
  file_path: string | null;
}

export interface ReviewIssueSummary {
  title: string;
  description: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  file_path: string | null;
  suggestion: string | null;
}

export interface RunDetail extends RunSummary {
  project_name: string | null;
  dependency_retry_count: number;
  testing_result: string;
  discovery_status: "not_recognized" | "recognized_no_tests" | "recognized_testable" | null;
  tests_discovered: boolean;
  tests_executed: boolean;
  verification_method: string | null;
  review_passed: boolean;
  review_score: number;
  review_auto_passed: boolean;
  review_auto_pass_reason: string | null;
  review_attempt_number: number;
  review_summary: string | null;
  review_issues: ReviewIssueSummary[];
  files_materialized: number;
  total_tests: number;
  passed_tests: number;
  failed_tests_count: number;
  failed_test_names: TestFailureSummary[];
  failure_classification: string | null;
  tester_summary: string | null;
}

export interface RunList {
  runs: RunSummary[];
  total_count: number;
  has_more: boolean;
}

export interface RunAccepted {
  run_id: string;
  status: string;
}

export type EventType =
  | "workflow_started"
  | "workflow_resumed"
  | "agent_started"
  | "agent_completed"
  | "testing_passed"
  | "testing_failed"
  | "review_passed"
  | "review_failed"
  | "reviewer_attempt_started"
  | "reviewer_attempt_completed"
  | "reviewer_repair_requested"
  | "reviewer_auto_passed"
  | "workflow_completed"
  | "workflow_completed_with_verification_issues"
  | "workflow_interrupted"
  | "workflow_failed"
  | "mcp_tool_call_started"
  | "mcp_tool_call_completed"
  | "mcp_tool_call_failed"
  | "agent_invocation_recorded"
  | "recovery_action_taken";

export interface WorkflowEventPayload {
  id?: number;
  run_id: string;
  event_type: EventType;
  agent: AgentType | null;
  message: string | null;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface RunProjectOut {
  run_id: string;
  project_name: string | null;
  project_description: string | null;
  objective: string | null;
  status: string;
  backend: string | null;
  frontend: string | null;
  database: string | null;
  deployment: string | null;
  requirements: string[];
  tech_stack: string[];
  output_directory: string | null;
}

export interface KnowledgeEntryOut {
  id: string;
  run_id: string;
  category: string;
  title: string;
  content: string;
  created_by: string;
  status: string;
  source_id: string | null;
  supersedes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectFileOut {
  path: string;
  size_bytes: number;
}

export interface ProjectFileList {
  run_id: string;
  files: ProjectFileOut[];
}

export interface ProjectFileContent {
  path: string;
  content: string;
}

export interface DocumentationFileOut {
  title: string;
  path: string;
  content: string;
  description: string | null;
  generating_agent: string | null;
  status: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DocumentationListResponse {
  documentation_summary: string | null;
  files: DocumentationFileOut[];
}

export interface ProjectAccepted {
  project_id: string;
  run_id: string;
  status: string;
}

export interface ProjectSummaryOut {
  id: string;
  name: string | null;
  status: string;
  run_count: number;
  latest_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetailOut extends ProjectSummaryOut {
  initial_prompt: string | null;
}

export interface ProjectListOut {
  projects: ProjectSummaryOut[];
  total_count: number;
  has_more: boolean;
}

export type ConversationRole = "human" | "ai" | "system" | string;

export interface ConversationMessageOut {
  role: ConversationRole;
  content: string;
}

export interface ConversationOut {
  project_id: string;
  messages: ConversationMessageOut[];
}

export type FileTreeNodeType = "file" | "folder";

export interface FileTreeNode {
  type: FileTreeNodeType;
  name: string;
  path: string;
  sizeBytes?: number;
  children?: FileTreeNode[];
}

export interface RepoFileNodeOut {
  type: FileTreeNodeType;
  name: string;
  path: string;
  size_bytes: number | null;
  children: RepoFileNodeOut[];
}

export interface RepoTreeResponse {
  run_id: string;
  tree: RepoFileNodeOut[];
}

export interface RepoFileRead {
  path: string;
  content: string;
  version: string;
}

export interface RepoFileWrite {
  path: string;
  version: string;
}

export interface ApiErrorBody {
  error: { type: string; message: string };
}

export interface UserOut {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export const TERMINAL_EVENT_TYPES: EventType[] = [
  "workflow_completed",
  "workflow_completed_with_verification_issues",
  "workflow_failed",
  "workflow_interrupted",
];

export function isResumableStatus(status: WorkflowStatus): boolean {
  return (
    status !== "completed" &&
    status !== "completed_with_verification_issues" &&
    status !== "failed"
  );
}

export type StatusFilterValue =
  | "initialized"
  | "running"
  | "waiting_for_user"
  | "completed"
  | "completed_with_verification_issues"
  | "failed"
  | "resumable"
  | "interrupted";

export const STATUS_FILTER_OPTIONS: { value: StatusFilterValue; label: string }[] = [
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "completed_with_verification_issues", label: "Verification issues" },
  { value: "failed", label: "Failed" },
  { value: "interrupted", label: "Interrupted / Waiting for input" },
  { value: "resumable", label: "Resumable" },
];

export type SortOption = "recently_updated" | "newest" | "oldest" | "duration" | "status";

export const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "recently_updated", label: "Recently updated" },
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "duration", label: "Duration" },
  { value: "status", label: "Needs attention first" },
];

export type MCPConnectionStatus =
  | "online"
  | "offline"
  | "unreachable"
  | "authentication_failed"
  | "timeout"
  | "disabled";

export interface MCPServerOut {
  id: string;
  display_name: string;
  description: string | null;
  transport: string;
  is_remote: boolean;
  endpoint: string;
  connection_status: MCPConnectionStatus;
  auth_type: string;
  auth_configured: boolean;
  tool_count: number;
  last_health_check: string | null;
  version: string | null;
  latency_ms: number | null;
}


export interface WorkflowEdgeOut {
  source: string;
  target: string;
  conditional: boolean;
}

export interface WorkflowGraphOut {
  nodes: AgentType[];
  edges: WorkflowEdgeOut[];
  repair_nodes: AgentType[];
}

export interface MCPToolOut {
  identity: string;
  server_name: string;
  tool_name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface MCPMetricsOut {
  server_name: string;
  total_executions: number;
  total_failures: number;
  active_requests: number;
  last_execution_at: string | null;
  connected_since: string | null;
}

export interface MCPExecuteResult {
  success: boolean;
  data: string | null;
  truncated: boolean;
  error: string | null;
}


export type RecoveryMode =
  | "resume"
  | "retry_agent"
  | "restart_from_checkpoint"
  | "restart_workflow"
  | "duplicate_and_retry";

export interface RecoveryRecommendationOut {
  mode: RecoveryMode;
  confidence: number;
  explanation: string;
}

export interface FailureDetailOut {
  run_id: string;
  is_failed: boolean;
  failed_agent: AgentType | null;
  last_successful_agent: AgentType | null;
  failed_at: string | null;
  test_retry_count: number;
  review_retry_count: number;
  error_message: string | null;
  failure_category: string | null;
  recovery_reason: string | null;
  provider: string | null;
  model: string | null;
  duration_ms: number | null;
  repeated_failure: boolean;
  last_checkpoint_id: string | null;
  last_checkpoint_timestamp: string | null;
  recommendation: RecoveryRecommendationOut | null;
}

export interface CheckpointOut {
  checkpoint_id: string;
  node_name: string | null;
  timestamp: string | null;
}

export interface CheckpointListOut {
  run_id: string;
  checkpoints: CheckpointOut[];
}

export interface TimelineEntryOut {
  agent: AgentType;
  attempt_number: number;
  status: "success" | "failure";
  duration_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
  provider: string | null;
  model: string | null;
  failure_category: string | null;
  recovery_reason: string | null;
}

export interface MCPCallOut {
  agent: AgentType;
  server_name: string;
  tool_name: string;
  success: boolean;
  duration_ms: number | null;
  occurred_at: string;
}

export interface TimelineOut {
  run_id: string;
  entries: TimelineEntryOut[];
  mcp_calls: MCPCallOut[];
}

export interface RunLogsOut {
  run_id: string;
  lines: string[];
  truncated: boolean;
}

export interface AgentStatsOut {
  agent: AgentType;
  total: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_duration_ms: number | null;
  avg_input_tokens: number | null;
  avg_output_tokens: number | null;
}

export interface ReliabilitySummaryOut {
  overall_total: number;
  overall_success_count: number;
  overall_success_rate: number;
  per_agent: AgentStatsOut[];
  failure_category_breakdown: Record<string, number>;
  recovery_reason_breakdown: Record<string, number>;
  provider_breakdown: Record<string, number>;
}

export interface AgentFailureOut {
  run_id: string;
  attempt_number: number;
  status: string;
  exception_type: string | null;
  failure_category: string | null;
  recovery_reason: string | null;
  error_message: string | null;
  provider: string | null;
  model: string | null;
  duration_ms: number | null;
}

export interface AgentDetailOut {
  agent: AgentType;
  stats: AgentStatsOut | null;
  recovery_reason_breakdown: Record<string, number>;
  recent_failures: AgentFailureOut[];
}
