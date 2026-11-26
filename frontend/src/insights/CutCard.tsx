import { cycleTitle } from "./CycleList";

import type { CycleGroup } from "@/api/types";
import { nodeName } from "@/graph/names";

export function CutCard({
  group,
  lines,
  onAsk,
}: {
  group: CycleGroup;
  lines: Map<string, string>;
  onAsk: (question: string) => void;
}) {
  const cut = group.suggested_cut;
  return (
    <section className="panel cut-card">
      <div className="label">Edge to remove</div>
      {cut?.links.map((l) => {
        const e = l.edges[0];
        const at = e ? `${nodeName(e.source)}:${e.line}` : "";
        return (
          <div key={`${l.source}->${l.target}`}>
            <p className="mono">{`${nodeName(l.source)} → ${nodeName(l.target)}`}</p>
            <pre className="mono">
              <span className="muted">{e?.line} </span>
              {lines.get(at) ?? at}
            </pre>
          </div>
        );
      })}
      <p className="muted">{cut?.method === "exact" ? "minimum feedback arc set" : "greedy (large group)"}</p>
      <p className="recommend">Recommendation only — Graphora never modifies your code.</p>
      <button type="button" onClick={() => onAsk(`How do I break the ${cycleTitle(group)} cycle?`)}>
        Ask agents about this
      </button>
    </section>
  );
}
