"use client";

import { CheckCircle2, Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import { ProjectGroupSection } from "@/components/dashboard/project-group-section";

export function ContinueWorking() {
  return (
    <>
      <ProjectGroupSection title="Continue working" icon={RotateCcw} status="resumable" accent />
      <ProjectGroupSection title="Running" icon={Loader2} status="running" />
      <ProjectGroupSection title="Failed" icon={TriangleAlert} status="failed" />
      <ProjectGroupSection
        title="Recently completed"
        icon={CheckCircle2}
        status="completed"
        sort="newest"
      />
    </>
  );
}
