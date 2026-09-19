import { CreateRunForm } from "@/components/dashboard/create-run-form";
import { ProjectTable } from "@/components/dashboard/project-table";
import { ContinueWorking } from "@/components/dashboard/continue-working";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-10">
      <section className="flex flex-col items-center gap-3 pt-10 text-center">
        <h1 className="text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          What should AgentForge build?
        </h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Go from idea to a working, tested application in minutes, with no setup and no boilerplate to write yourself.
        </p>
      </section>

      <section className="mx-auto w-full max-w-2xl">
        <CreateRunForm />
      </section>

      <ContinueWorking />

      <section className="mx-auto w-full max-w-2xl">
        <h2 className="mb-3 font-mono text-xs font-medium tracking-wide text-muted-foreground uppercase">
          All projects
        </h2>
        <ProjectTable />
      </section>
    </div>
  );
}
