import { useState } from "react";

import type { CoverageFile } from "@/api/graph.gen";

export interface TreeNode {
  name: string;
  path: string;
  file?: CoverageFile;
  children: TreeNode[];
}

export function buildTree(files: CoverageFile[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", children: [] };
  for (const f of [...files].sort((a, b) => (a.path < b.path ? -1 : 1))) {
    let at = root;
    const parts = f.path.split("/");
    parts.forEach((name, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let next = at.children.find((c) => c.name === name && i < parts.length - 1 === !c.file);
      if (!next) {
        next = { name, path, children: [], ...(i === parts.length - 1 ? { file: f } : {}) };
        at.children.push(next);
      }
      at = next;
    });
  }
  const order = (nodes: TreeNode[]): TreeNode[] =>
    nodes
      .map((n) => ({ ...n, children: order(n.children) }))
      .sort((a, b) => (!a.file === !b.file ? (a.name < b.name ? -1 : 1) : a.file ? 1 : -1));
  return order(root.children);
}

function Branch({
  node,
  selected,
  onOpen,
}: {
  node: TreeNode;
  selected: string | null;
  onOpen: (path: string) => void;
}) {
  const [open, setOpen] = useState(selected?.startsWith(`${node.path}/`) ?? false);
  if (node.file) {
    const status = node.file.status;
    return (
      <li>
        <button
          type="button"
          className="tree-file"
          aria-current={selected === node.path ? "true" : undefined}
          onClick={() => onOpen(node.path)}
        >
          <span className={status === "analyzed" ? "" : status === "detected_only" ? "detected" : "not-code"}>
            {node.name}
          </span>
        </button>
      </li>
    );
  }
  return (
    <li>
      <button type="button" className="tree-folder" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} {node.name}
      </button>
      {open && (
        <ul>
          {node.children.map((c) => (
            <Branch key={c.path} node={c} selected={selected} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function FileTree({
  files,
  selected,
  onOpen,
}: {
  files: CoverageFile[];
  selected: string | null;
  onOpen: (path: string) => void;
}) {
  return (
    <nav className="file-tree panel" aria-label="Files">
      <div className="label">Files</div>
      <ul>
        {buildTree(files).map((n) => (
          <Branch key={n.path} node={n} selected={selected} onOpen={onOpen} />
        ))}
      </ul>
    </nav>
  );
}
