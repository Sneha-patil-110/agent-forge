"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { createProject } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const EXAMPLES = [
  "Build a FastAPI expense tracker with JWT auth and a PostgreSQL backend",
  "Create a CLI tool that converts Markdown notes into a static site",
  "Build a Slack bot that summarizes long threads on demand",
  "Create a rate-limited URL shortener service with click analytics",
];

export function CreateRunForm() {
  const [request, setRequest] = useState("");
  const router = useRouter();
  const queryClient = useQueryClient();

  const [placeholder, setPlaceholder] = useState(EXAMPLES[0]);

  useEffect(() => {
    setPlaceholder(EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)]);
  }, []);

  const mutation = useMutation({
    mutationFn: (text: string) => createProject(text),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["dashboard-projects"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/projects/${data.project_id}`);
    },
    onError: (error: Error) => {
      toast.error("Couldn't start the project", { description: error.message });
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = request.trim();
    if (!trimmed || mutation.isPending) return;
    mutation.mutate(trimmed);
  }

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="glow-ember surface-card relative overflow-hidden rounded-2xl p-1.5 has-[textarea:focus-visible]:ring-2 has-[textarea:focus-visible]:ring-ring/50"
    >
      <div className="rounded-xl bg-surface-2/60 p-4">
        <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          <span className="size-1.5 rounded-full bg-primary" />
          Describe what you want built
        </div>
        <Textarea
          value={request}
          onChange={(event) => setRequest(event.target.value)}
          placeholder={placeholder}
          rows={3}
          disabled={mutation.isPending}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              handleSubmit(event);
            }
          }}
          className="resize-none border-none bg-transparent px-0 text-base shadow-none focus-visible:ring-0"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className="font-mono text-[11px] text-muted-foreground/80">
            {"⌘"}/Ctrl + Enter to start
          </span>
          <Button
            type="submit"
            size="sm"
            isLoading={mutation.isPending}
            disabled={!request.trim()}
            className="gap-1.5"
          >
            {mutation.isPending ? (
              "Starting"
            ) : (
              <>
                Build it
                <ArrowUp className="size-3.5 -rotate-45" />
              </>
            )}
          </Button>
        </div>
      </div>
    </motion.form>
  );
}
