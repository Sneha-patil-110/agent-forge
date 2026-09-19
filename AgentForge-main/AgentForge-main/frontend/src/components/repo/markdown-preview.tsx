"use client";

import { useRef, useState } from "react";
import type { editor } from "monaco-editor";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Columns2, Eye } from "lucide-react";
import { cn } from "@/lib/utils";
import { CodeEditor } from "@/components/repo/code-editor";
import { markdownComponents } from "@/components/ui/markdown-components";

type ViewMode = "preview" | "split";

export function MarkdownPreview({
  path,
  content,
  isDirty,
  isSaving,
  onChange,
  onSave,
}: {
  path: string;
  content: string;
  isDirty: boolean;
  isSaving: boolean;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  const [mode, setMode] = useState<ViewMode>("preview");
  const editorInstanceRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const syncingRef = useRef(false);

  function syncPreviewToEditor(instance: editor.IStandaloneCodeEditor) {
    const preview = previewRef.current;
    if (syncingRef.current || !preview) return;

    const scrollRange = instance.getScrollHeight() - instance.getLayoutInfo().height;
    if (scrollRange <= 0) return;

    const fraction = instance.getScrollTop() / scrollRange;
    syncingRef.current = true;
    preview.scrollTop = fraction * (preview.scrollHeight - preview.clientHeight);
    requestAnimationFrame(() => {
      syncingRef.current = false;
    });
  }

  function syncEditorToPreview() {
    const preview = previewRef.current;
    const instance = editorInstanceRef.current;
    if (syncingRef.current || !preview || !instance) return;

    const scrollRange = preview.scrollHeight - preview.clientHeight;
    if (scrollRange <= 0) return;

    const fraction = preview.scrollTop / scrollRange;
    syncingRef.current = true;
    instance.setScrollTop(fraction * (instance.getScrollHeight() - instance.getLayoutInfo().height));
    requestAnimationFrame(() => {
      syncingRef.current = false;
    });
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-end gap-1 border-b border-border/60 bg-surface/40 px-2 py-1">
        <button
          onClick={() => setMode("preview")}
          className={cn(
            "flex items-center gap-1 rounded-md px-2 py-1 text-xs",
            mode === "preview" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
          )}
        >
          <Eye className="size-3.5" />
          Preview
        </button>
        <button
          onClick={() => setMode("split")}
          className={cn(
            "flex items-center gap-1 rounded-md px-2 py-1 text-xs",
            mode === "split" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
          )}
        >
          <Columns2 className="size-3.5" />
          Split
        </button>
      </div>
      <div className={cn("min-h-0 flex-1", mode === "split" && "grid grid-cols-2")}>
        {mode === "split" && (
          <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-r border-border/60">
            <CodeEditor
              path={path}
              content={content}
              isDirty={isDirty}
              isSaving={isSaving}
              onChange={onChange}
              onSave={onSave}
              onEditorReady={(instance) => {
                editorInstanceRef.current = instance;
                instance.onDidScrollChange(() => syncPreviewToEditor(instance));
              }}
            />
          </div>
        )}
        <div
          ref={previewRef}
          onScroll={mode === "split" ? syncEditorToPreview : undefined}
          className="h-full min-h-0 overflow-y-auto px-8 py-6"
        >
          <article className="prose prose-invert prose-sm max-w-2xl prose-pre:bg-surface-2 prose-pre:border prose-pre:border-border/60 prose-code:text-primary prose-a:text-primary">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {content}
            </ReactMarkdown>
          </article>
        </div>
      </div>
    </div>
  );
}
