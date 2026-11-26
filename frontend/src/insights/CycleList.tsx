import type { CycleGroup } from "@/api/types";
import { nodeName } from "@/graph/names";

function part(file: string): string {
  const path = nodeName(file);
  const slash = path.indexOf("/");
  return slash < 0 ? path.replace(/\.[^.]+$/, "") : path.slice(0, slash);
}

export function cycleTitle(group: CycleGroup): string {
  const parts = [...new Set(group.files.map(part))];
  if (parts.length === 1) return group.files.map((f) => nodeName(f).split("/").pop()).join(" ⇄ ");
  if (parts.length === 2) return parts.join(" ⇄ ");
  return [...parts, parts[0]].join(" → ");
}

export function CycleList({
  groups,
  selected,
  onSelect,
}: {
  groups: CycleGroup[];
  selected: number | null;
  onSelect: (i: number) => void;
}) {
  if (groups.length === 0) return <p className="muted">No cycles in this snapshot.</p>;
  return (
    <ul className="cycle-list">
      {groups.map((g, i) => (
        <li key={g.files.join("|")} aria-current={selected === i ? "true" : undefined}>
          <button type="button" onClick={() => onSelect(i)}>
            <strong>{cycleTitle(g)}</strong>
            <span className="pill cycle">
              {g.cycle.length} {g.cycle.length === 1 ? "edge" : "edges"}
            </span>
            {g.type_only && <span className="pill">type-only</span>}
            <span className="mono muted">{g.files.map(nodeName).join(g.files.length === 2 ? " ⇄ " : " → ")}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
