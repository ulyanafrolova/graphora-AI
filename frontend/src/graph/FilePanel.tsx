import { nodeName } from "./names";

import type { Answer, Files, Item } from "@/api/types";

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
}

function Links({ items, testId, onSelect }: { items: Item[]; testId: string; onSelect: (id: string) => void }) {
  return (
    <ul className="rows" data-testid={testId}>
      {items.map((i) => (
        <li key={i.node}>
          {i.node.startsWith("file:") ? (
            <button type="button" className="link mono" onClick={() => onSelect(i.node)}>
              {nodeName(i.node)}
            </button>
          ) : (
            <span className="mono">{nodeName(i.node)}</span>
          )}
          <span className={`pill ${i.kind === "external" ? "" : i.confidence}`}>
            {i.kind === "external" ? "external" : i.confidence}
          </span>
        </li>
      ))}
      {items.length === 0 && <li className="muted">none</li>}
    </ul>
  );
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
      <div className="label">Imports · {neighbors?.outgoing?.length ?? 0}</div>
      <Links items={neighbors?.outgoing ?? []} testId="dependencies" onSelect={props.onSelect} />
      <div className="label">Imported by · {neighbors?.incoming?.length ?? 0}</div>
      <Links items={neighbors?.incoming ?? []} testId="dependents" onSelect={props.onSelect} />
      {loops.map((g) => (
        <p key={g.files.join("|")} className="issue">
          Cycle: {g.files.map(nodeName).join(g.files.length === 2 ? " ⇄ " : " → ")}
        </p>
      ))}
    </aside>
  );
}
