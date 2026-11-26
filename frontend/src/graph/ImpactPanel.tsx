import { paletteColor } from "./style";

import type { Answer } from "@/api/types";

export interface ComponentImpact {
  id: string;
  name: string;
  resolved: number;
  heuristic: number;
  color: number;
}

/** Impact items grouped by the component that holds them (a count over the answer, research R2). */
export function impactByComponent(impact: Answer, components: Answer): ComponentImpact[] {
  const comps = components.components ?? [];
  const where = new Map(comps.flatMap((c, i) => c.files.map((f) => [f, i] as const)));
  const rows = comps.map((c, i) => ({ id: c.id, name: c.name, resolved: 0, heuristic: 0, color: i + 1 }));
  for (const item of impact.items ?? []) {
    const i = where.get(item.node);
    const row = i === undefined ? undefined : rows[i];
    if (row === undefined) continue;
    if (item.confidence === "heuristic") row.heuristic += 1;
    else row.resolved += 1;
  }
  return rows
    .filter((r) => r.resolved + r.heuristic > 0)
    .sort((a, b) => b.resolved + b.heuristic - (a.resolved + a.heuristic) || (a.name < b.name ? -1 : 1));
}

export function ImpactPanel({ answer, components }: { answer: Answer; components: Answer }) {
  const rows = impactByComponent(answer, components);
  const max = Math.max(1, ...rows.map((r) => r.resolved + r.heuristic));
  const more = answer.total - (answer.items?.length ?? 0);
  return (
    <section className="impact-panel">
      <div className="label">Impact mode</div>
      {answer.total === 0 ? (
        <p className="muted">Nothing depends on this file.</p>
      ) : (
        <>
          <p className="impact-total">
            <strong>{answer.total}</strong>{" "}
            <span>
              files in {rows.length} {rows.length === 1 ? "component" : "components"}
            </span>
          </p>
          <ul className="bars">
            {rows.map((r) => (
              <li key={r.id}>
                <span>{r.name}</span>
                <span className={r.resolved === 0 ? "heuristic-text" : ""}>
                  {r.resolved > 0 ? r.resolved : ""}
                  {r.heuristic > 0 ? `${r.resolved > 0 ? " + " : ""}~${r.heuristic} heuristic` : ""}
                </span>
                <i
                  aria-hidden="true"
                  style={{
                    width: `${(100 * (r.resolved + r.heuristic)) / max}%`,
                    background: r.resolved === 0 ? "var(--heuristic)" : paletteColor(r.color),
                  }}
                />
              </li>
            ))}
          </ul>
          {answer.truncated && <p className="muted">and {more} more (the list is cut)</p>}
        </>
      )}
    </section>
  );
}
