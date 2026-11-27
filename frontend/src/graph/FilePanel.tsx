import type { ReactNode } from "react";

import { ItemLinks } from "./ItemLinks";
import { nodeName } from "./names";

import type { Answer, Files } from "@/api/types";

export interface FilePanelProps {
  node: string;
  files: Files | undefined;
  keyFiles: Answer | undefined;
  hotspots: Answer | undefined;
  neighbors: Answer | undefined;
  cycles: Answer | undefined;
  impact: boolean;
  onToggleImpact: () => void;
  onOpenCode: () => void;
  onSelect: (id: string) => void;
  children?: ReactNode;
}

export function FilePanel(props: FilePanelProps) {
  const { node, files, keyFiles, hotspots, neighbors, cycles, impact } = props;
  const path = nodeName(node);
  const lines = files?.files.find((f) => f.path === path)?.line_count;
  const keyRank = (keyFiles?.items ?? []).findIndex((i) => i.node === node) + 1;
  const hotRank = (hotspots?.items ?? []).findIndex((i) => i.node === node) + 1;
  const meta = [
    lines !== undefined && `${lines} LOC`,
    keyRank > 0 && `key file #${keyRank}`,
    hotRank > 0 && `hotspot #${hotRank}`,
  ].filter(Boolean);
  const loops = (cycles?.groups ?? []).filter((g) => g.files.includes(node));

  return (
    <aside className="side-panel">
      <div className="label">Selected file</div>
      <h2 className="mono">{path}</h2>
      <p className="muted">{meta.join(" · ")}</p>
      <div className="actions">
        <button type="button" aria-pressed={impact} className={impact ? "primary" : ""} onClick={props.onToggleImpact}>
          Impact mode
        </button>
        <button type="button" onClick={props.onOpenCode}>
          Open code
        </button>
      </div>
      {props.children}
      <div className="label">Imports{neighbors && ` · ${neighbors.outgoing?.length ?? 0}`}</div>
      <ItemLinks items={neighbors && (neighbors.outgoing ?? [])} testId="dependencies" onOpen={props.onSelect} />
      <div className="label">Imported by{neighbors && ` · ${neighbors.incoming?.length ?? 0}`}</div>
      <ItemLinks items={neighbors && (neighbors.incoming ?? [])} testId="dependents" onOpen={props.onSelect} />
      {loops.map((g) => (
        <p key={g.files.join("|")} className="issue">
          Cycle: {g.files.map(nodeName).join(g.files.length === 2 ? " ⇄ " : " → ")}
        </p>
      ))}
    </aside>
  );
}
