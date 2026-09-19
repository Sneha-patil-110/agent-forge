import { ReliabilityDashboard } from "@/components/reliability/reliability-dashboard";

export default function ReliabilityPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Reliability</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Success rates, failure causes, and provider/token usage across every agent invocation.
        </p>
      </div>
      <ReliabilityDashboard />
    </div>
  );
}
