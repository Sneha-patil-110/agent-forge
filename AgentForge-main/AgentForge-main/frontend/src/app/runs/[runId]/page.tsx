import { RunView } from "@/components/run/run-view";

export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;

  return <RunView key={runId} runId={runId} />;
}
