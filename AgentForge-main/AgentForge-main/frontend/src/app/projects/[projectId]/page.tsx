import { ProjectWorkspace } from "@/components/workspace/project-workspace";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;

  return <ProjectWorkspace key={projectId} projectId={projectId} />;
}
