"use client";

import dynamic from "next/dynamic";
import { useRef } from "react";
import type { Monaco } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { Check, Circle, Download, Loader2, WrapText } from "lucide-react";
import { languageFromPath } from "@/lib/file-icons";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((mod) => mod.default), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

function defineForgeTheme(monaco: Monaco) {
  monaco.editor.defineTheme("forge-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "6b7280", fontStyle: "italic" },
      { token: "keyword", foreground: "e0a35c" },
      { token: "string", foreground: "9fd88b" },
      { token: "number", foreground: "d8a86b" },
    ],
    colors: {
      "editor.background": "#181614",
      "editor.foreground": "#f2efe9",
      "editor.lineHighlightBackground": "#221f1c",
      "editorLineNumber.foreground": "#5c574f",
      "editorLineNumber.activeForeground": "#c9c2b6",
      "editor.selectionBackground": "#e0a35c33",
      "editorCursor.foreground": "#e0a35c",
      "editorGutter.background": "#181614",
      "editorWidget.background": "#211e1b",
      "editorWidget.border": "#33302b",
      "minimap.background": "#161412",
    },
  });
}

export function CodeEditor({
  path,
  content,
  isDirty,
  isSaving,
  onChange,
  onSave,
  onDownload,
  onEditorReady,
}: {
  path: string;
  content: string;
  isDirty: boolean;
  isSaving: boolean;
  onChange: (value: string) => void;
  onSave: () => void;
  onDownload?: (path: string) => void;
  onEditorReady?: (instance: editor.IStandaloneCodeEditor) => void;
}) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const language = languageFromPath(path);
  const [wordWrap, setWordWrap] = usePersistedState<boolean>("agentforge:wordwrap", true);

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center justify-between gap-1.5 border-b border-border/60 bg-surface/60 px-3 py-1.5 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          {isSaving ? (
            <>
              <Loader2 className="size-3 animate-spin" />
              Saving…
            </>
          ) : isDirty ? (
            <>
              <Circle className="size-2 fill-primary text-primary" />
              Unsaved changes
            </>
          ) : (
            <>
              <Check className="size-3 text-status-completed" />
              Saved
            </>
          )}
        </span>
        <div className="flex items-center gap-1">
          <span className="mr-1 text-muted-foreground/70">{"⌘"}/Ctrl + S to save · Ctrl+F to search</span>
          <Button
            size="icon"
            variant="ghost"
            className={cn("size-6", wordWrap && "text-primary")}
            title={wordWrap ? "Disable word wrap" : "Enable word wrap"}
            aria-label={wordWrap ? "Disable word wrap" : "Enable word wrap"}
            aria-pressed={wordWrap}
            onClick={() => setWordWrap((current) => !current)}
          >
            <WrapText className="size-3.5" />
          </Button>
          {onDownload && (
            <Button
              size="icon"
              variant="ghost"
              className="size-6"
              title="Download file"
              aria-label="Download file"
              onClick={() => onDownload(path)}
            >
              <Download className="size-3.5" />
            </Button>
          )}
          <Button
            size="xs"
            variant={isDirty ? "default" : "ghost"}
            disabled={!isDirty || isSaving}
            onClick={onSave}
          >
            Save
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <MonacoEditor
          key={path}
          path={path}
          language={language}
          value={content}
          theme="forge-dark"
          onChange={(value) => onChange(value ?? "")}
          onMount={(instance, monaco) => {
            editorRef.current = instance;
            onEditorReady?.(instance);
            defineForgeTheme(monaco);
            monaco.editor.setTheme("forge-dark");

            instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
              onSave();
            });

            if (language === "json") {
              instance.getAction("editor.action.formatDocument")?.run();
            }
          }}
          beforeMount={defineForgeTheme}
          options={{
            readOnly: false,
            minimap: { enabled: true },
            fontSize: 13,
            fontLigatures: true,
            wordWrap: wordWrap ? "on" : "off",
            automaticLayout: true,
            renderLineHighlight: "all",
            scrollBeyondLastLine: false,
            smoothScrolling: true,
            folding: true,
            padding: { top: 12 },
          }}
        />
      </div>
    </div>
  );
}
