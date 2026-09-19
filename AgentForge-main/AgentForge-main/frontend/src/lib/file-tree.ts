import type { FileTreeNode, ProjectFileOut, RepoFileNodeOut } from "@/lib/types";

export function fromRepoTree(nodes: RepoFileNodeOut[]): FileTreeNode[] {
  return nodes.map((node) => ({
    type: node.type,
    name: node.name,
    path: node.path,
    sizeBytes: node.size_bytes ?? undefined,
    children: node.type === "folder" ? fromRepoTree(node.children) : undefined,
  }));
}

export function buildFileTree(files: ProjectFileOut[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];

  for (const file of files) {
    const segments = file.path.split("/").filter(Boolean);
    let level = root;
    let pathSoFar = "";

    segments.forEach((segment, index) => {
      pathSoFar = pathSoFar ? `${pathSoFar}/${segment}` : segment;
      const isLeaf = index === segments.length - 1;

      let node = level.find((candidate) => candidate.name === segment);

      if (!node) {
        node = isLeaf
          ? { type: "file", name: segment, path: pathSoFar, sizeBytes: file.size_bytes }
          : { type: "folder", name: segment, path: pathSoFar, children: [] };
        level.push(node);
      }

      if (!isLeaf) {
        node.children ??= [];
        level = node.children;
      }
    });
  }

  sortTree(root);
  return root;
}

function sortTree(nodes: FileTreeNode[]): void {
  nodes.sort((a, b) => {
    if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  for (const node of nodes) {
    if (node.children) sortTree(node.children);
  }
}

export function flattenFiles(nodes: FileTreeNode[]): FileTreeNode[] {
  const result: FileTreeNode[] = [];

  const walk = (list: FileTreeNode[]) => {
    for (const node of list) {
      if (node.type === "file") {
        result.push(node);
      } else if (node.children) {
        walk(node.children);
      }
    }
  };

  walk(nodes);
  return result;
}

export interface VisibleNode {
  node: FileTreeNode;
  depth: number;
}

export function flattenVisible(
  nodes: FileTreeNode[],
  expanded: ReadonlySet<string>,
  depth = 0,
): VisibleNode[] {
  const result: VisibleNode[] = [];

  for (const node of nodes) {
    result.push({ node, depth });

    if (node.type === "folder" && expanded.has(node.path) && node.children) {
      result.push(...flattenVisible(node.children, expanded, depth + 1));
    }
  }

  return result;
}

export function ancestorFolders(path: string): string[] {
  const segments = path.split("/").filter(Boolean);
  const folders: string[] = [];
  let current = "";

  for (let i = 0; i < segments.length - 1; i += 1) {
    current = current ? `${current}/${segments[i]}` : segments[i];
    folders.push(current);
  }

  return folders;
}
