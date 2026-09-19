import { Skeleton } from "@/components/ui/skeleton";

export default function ProjectLoading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}
