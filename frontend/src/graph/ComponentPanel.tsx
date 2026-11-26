import { nodeName } from "./names";

import type { Answer, Component, Files } from "@/api/types";

export interface ComponentPanelProps {
  component: Component | null;
  components: Answer;
  keyFiles: Answer | undefined;
  cycles: Answer | undefined;
  files: Files | undefined;
  onExpand: () => void;
  onAsk: (question: string) => void;
  onSelect: (id: string) => void;
}

export function ComponentPanel({
  component,
  components,
  keyFiles,
  cycles,
  files,
  onExpand,
  onAsk,
  onSelect,
}: ComponentPanelProps) {
  if (component === null) return null;
  const comps = components.components ?? [];
  const links = components.links ?? [];
  const members = new Set(component.files);
  const lines = new Map((files?.files ?? []).map((f) => [`file:${f.path}`, f.line_count]));
  const loc = component.files.reduce((sum, f) => sum + (lines.get(f) ?? 0), 0);
  const dependsOn = new Set(links.filter((l) => l.source === component.id).map((l) => l.target)).size;
  const usedBy = new Set(links.filter((l) => l.target === component.id).map((l) => l.source)).size;

  const keyIndex = new Map((keyFiles?.items ?? []).map((item, i) => [item.node, i]));
  const best = (c: Component) => Math.min(...c.files.map((f) => keyIndex.get(f) ?? Infinity));
  const ranked = [...comps].sort((a, b) => best(a) - best(b) || (a.id < b.id ? -1 : 1));
  const rank = ranked.findIndex((c) => c.id === component.id) + 1;
  const keys = (keyFiles?.items ?? []).filter((item) => members.has(item.node)).slice(0, 5);

  const owner = new Map(comps.flatMap((c) => c.files.map((f) => [f, c] as const)));
  const issues = (cycles?.groups ?? [])
    .filter((g) => g.files.some((f) => members.has(f)))
    .map((g) => {
      const others = [...new Set(g.files.map((f) => owner.get(f)).filter((c) => c && c.id !== component.id))];
      const edges = `${g.cycle.length} ${g.cycle.length === 1 ? "edge" : "edges"}`;
      return others.length
        ? `Cycle with ${others.map((c) => c?.name).join(", ")} (${edges})`
        : `Cycle inside ${component.name} (${edges})`;
    });

  return (
    <aside className="side-panel">
      <div className="label">Component</div>
      <h2>{component.name}</h2>
      <p className="muted">
        {component.file_count} {component.file_count === 1 ? "file" : "files"} · {loc} LOC
      </p>
      <div className="stats">
        <div className="stat" data-testid="depends-on">
          <span className="muted">Depends on</span>
          <strong>{dependsOn}</strong>
        </div>
        <div className="stat" data-testid="used-by">
          <span className="muted">Used by</span>
          <strong>{usedBy}</strong>
        </div>
        <div className="stat" data-testid="centrality">
          <span className="muted">Centrality</span>
          <strong>#{rank}</strong>
        </div>
      </div>
      {keys.length > 0 && (
        <>
          <div className="label">Key files</div>
          <ul className="rows">
            {keys.map((k) => (
              <li key={k.node} data-testid="key-file">
                <button type="button" className="link mono" onClick={() => onSelect(k.node)}>
                  {nodeName(k.node)}
                </button>
                <span className="muted">in {k.transitive_dependents}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {issues.length > 0 && (
        <>
          <div className="label">Issues</div>
          {issues.map((text) => (
            <p key={text} className="issue">
              {text}
            </p>
          ))}
        </>
      )}
      <div className="actions">
        <button type="button" className="primary" onClick={onExpand}>
          Expand component
        </button>
        <button type="button" onClick={() => onAsk(`Explain the ${component.name} component`)}>
          Ask about {component.name}
        </button>
      </div>
    </aside>
  );
}
