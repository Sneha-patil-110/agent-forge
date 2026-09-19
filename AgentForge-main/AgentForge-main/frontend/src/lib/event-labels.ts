import type { WorkflowEventPayload } from "@/lib/types";

export function describeEvent(event: WorkflowEventPayload): string {
  if (event.message) return event.message;

  const agent = event.agent ? event.agent : null;

  switch (event.event_type) {
    case "workflow_started":
      return "Workflow started";
    case "workflow_resumed":
      return "Workflow resumed";
    case "agent_started":
      return `${agent} agent started`;
    case "agent_completed":
      return `${agent} agent completed`;
    case "testing_passed":
      return "Tests passed";
    case "testing_failed":
      return "Tests failed";
    case "review_passed":
      return "Review passed";
    case "review_failed":
      return "Review requested changes";
    case "reviewer_attempt_started":
      return `Review attempt ${event.metadata?.attempt ?? ""}`.trim();
    case "reviewer_attempt_completed":
      return event.metadata?.passed
        ? "Review attempt passed"
        : `Review attempt ${event.metadata?.attempt ?? ""} rejected`.trim();
    case "reviewer_repair_requested":
      return "Review rejected; requesting repair";
    case "reviewer_auto_passed":
      return `Review passed with warnings after ${event.metadata?.attempts ?? 2} attempts`;
    case "workflow_completed":
      return "Workflow completed";
    case "workflow_completed_with_verification_issues":
      return "Repository ready; verification incomplete";
    case "workflow_interrupted":
      return "Workflow interrupted";
    case "workflow_failed":
      return "Workflow failed";
    case "mcp_tool_call_started":
      return `Calling tool ${event.metadata?.tool ?? ""}`.trim();
    case "mcp_tool_call_completed":
      return `Tool call completed ${event.metadata?.tool ?? ""}`.trim();
    case "mcp_tool_call_failed":
      return `Tool call failed ${event.metadata?.tool ?? ""}`.trim();
    case "recovery_action_taken":
      return `Recovery: ${String(event.metadata?.mode ?? "").replace(/_/g, " ")}`;
    default:
      return event.event_type;
  }
}

export function describeEventAsStatus(event: WorkflowEventPayload): string {
  const agent = event.agent ? event.agent : null;

  switch (event.event_type) {
    case "workflow_started":
      return "Starting…";
    case "workflow_resumed":
      return "Resuming…";
    case "agent_started":
      return agentStatusLabel(agent);
    case "agent_completed":
      return `${capitalize(agent)} done`;
    case "testing_passed":
      return "Tests passed";
    case "testing_failed":
      return "Tests failed, repairing…";
    case "review_passed":
      return "Review passed";
    case "review_failed":
      return "Addressing review feedback…";
    case "reviewer_auto_passed":
      return "Review passed with warnings";
    case "workflow_completed":
      return "Done";
    case "workflow_completed_with_verification_issues":
      return "Done, with verification issues";
    case "workflow_interrupted":
      return "Interrupted";
    case "workflow_failed":
      return "Failed";
    default:
      return describeEvent(event);
  }
}

function capitalize(value: string | null): string {
  if (!value) return "Agent";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function agentStatusLabel(agent: string | null): string {
  switch (agent) {
    case "analysis":
      return "Analyzing your request…";
    case "planner":
      return "Planning changes…";
    case "architect":
      return "Designing architecture…";
    case "developer":
      return "Writing code…";
    case "static_validation":
      return "Checking for obvious issues…";
    case "tester":
      return "Running tests…";
    case "debugger":
      return "Debugging a failure…";
    case "reviewer":
      return "Reviewing the implementation…";
    case "documentation":
      return "Writing documentation…";
    default:
      return "Working…";
  }
}
