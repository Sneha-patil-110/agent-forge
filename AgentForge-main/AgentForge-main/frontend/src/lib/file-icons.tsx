import {
  FileCode2,
  FileCog,
  FileJson2,
  FileText,
  FileType2,
  FileTerminal,
  Database,
  Image,
  type LucideIcon,
} from "lucide-react";

interface FileIconSpec {
  icon: LucideIcon;
  color: string;
}

const BY_EXTENSION: Record<string, FileIconSpec> = {
  py: { icon: FileCode2, color: "text-[oklch(0.75_0.16_230)]" },
  js: { icon: FileCode2, color: "text-[oklch(0.8_0.17_95)]" },
  jsx: { icon: FileCode2, color: "text-[oklch(0.75_0.16_200)]" },
  ts: { icon: FileCode2, color: "text-[oklch(0.72_0.14_250)]" },
  tsx: { icon: FileCode2, color: "text-[oklch(0.75_0.16_200)]" },
  go: { icon: FileCode2, color: "text-[oklch(0.75_0.16_200)]" },
  rs: { icon: FileCode2, color: "text-[oklch(0.65_0.18_45)]" },
  java: { icon: FileCode2, color: "text-[oklch(0.7_0.18_35)]" },
  rb: { icon: FileCode2, color: "text-[oklch(0.65_0.2_25)]" },
  php: { icon: FileCode2, color: "text-[oklch(0.65_0.16_280)]" },
  c: { icon: FileCode2, color: "text-[oklch(0.7_0.1_250)]" },
  cpp: { icon: FileCode2, color: "text-[oklch(0.7_0.1_250)]" },
  h: { icon: FileCode2, color: "text-[oklch(0.7_0.1_250)]" },
  sql: { icon: Database, color: "text-[oklch(0.72_0.14_250)]" },
  json: { icon: FileJson2, color: "text-[oklch(0.8_0.17_95)]" },
  yml: { icon: FileCog, color: "text-muted-foreground" },
  yaml: { icon: FileCog, color: "text-muted-foreground" },
  toml: { icon: FileCog, color: "text-muted-foreground" },
  ini: { icon: FileCog, color: "text-muted-foreground" },
  env: { icon: FileCog, color: "text-muted-foreground" },
  md: { icon: FileText, color: "text-foreground/70" },
  mdx: { icon: FileText, color: "text-foreground/70" },
  txt: { icon: FileText, color: "text-muted-foreground" },
  html: { icon: FileType2, color: "text-[oklch(0.65_0.2_25)]" },
  css: { icon: FileType2, color: "text-[oklch(0.72_0.14_250)]" },
  scss: { icon: FileType2, color: "text-[oklch(0.65_0.2_340)]" },
  xml: { icon: FileType2, color: "text-muted-foreground" },
  sh: { icon: FileTerminal, color: "text-status-completed" },
  bash: { icon: FileTerminal, color: "text-status-completed" },
  png: { icon: Image, color: "text-[oklch(0.65_0.2_340)]" },
  jpg: { icon: Image, color: "text-[oklch(0.65_0.2_340)]" },
  jpeg: { icon: Image, color: "text-[oklch(0.65_0.2_340)]" },
  svg: { icon: Image, color: "text-[oklch(0.65_0.2_340)]" },
  gif: { icon: Image, color: "text-[oklch(0.65_0.2_340)]" },
};

const BY_FILENAME: Record<string, FileIconSpec> = {
  dockerfile: { icon: FileCog, color: "text-[oklch(0.72_0.14_250)]" },
  makefile: { icon: FileTerminal, color: "text-status-completed" },
  ".gitignore": { icon: FileCog, color: "text-muted-foreground" },
  ".env": { icon: FileCog, color: "text-muted-foreground" },
};

const DEFAULT_ICON: FileIconSpec = { icon: FileText, color: "text-muted-foreground" };

export function getFileIcon(name: string): FileIconSpec {
  const lower = name.toLowerCase();
  if (BY_FILENAME[lower]) return BY_FILENAME[lower];

  const extension = lower.includes(".") ? lower.split(".").pop() : undefined;
  if (extension && BY_EXTENSION[extension]) return BY_EXTENSION[extension];

  return DEFAULT_ICON;
}

export function languageFromPath(path: string): string {
  const extension = path.toLowerCase().split(".").pop() ?? "";

  const map: Record<string, string> = {
    py: "python",
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    json: "json",
    md: "markdown",
    mdx: "markdown",
    html: "html",
    css: "css",
    scss: "scss",
    yml: "yaml",
    yaml: "yaml",
    toml: "toml",
    sql: "sql",
    sh: "shell",
    bash: "shell",
    go: "go",
    rs: "rust",
    java: "java",
    rb: "ruby",
    php: "php",
    c: "c",
    cpp: "cpp",
    h: "c",
    xml: "xml",
  };

  return map[extension] ?? "plaintext";
}

export function isMarkdown(path: string): boolean {
  return languageFromPath(path) === "markdown";
}
