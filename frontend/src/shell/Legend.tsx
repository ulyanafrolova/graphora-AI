export const LEGEND = [
  { key: "resolved", label: "resolved link (written in code)" },
  { key: "heuristic", label: "heuristic link (likely)" },
  { key: "unresolved", label: "unresolved import" },
  { key: "cycle", label: "cycle" },
  { key: "impact", label: "impact path" },
  { key: "hypothesis", label: "hypothesis (not proven)" },
  { key: "verified", label: "verified fact" },
  { key: "external", label: "external package" },
] as const;

export type LegendKey = (typeof LEGEND)[number]["key"];

export function Legend({ only }: { only?: LegendKey[] }) {
  const rows = only === undefined ? LEGEND : LEGEND.filter((r) => only.includes(r.key));
  return (
    <ul className="legend">
      {rows.map((r) => (
        <li key={r.key}>
          <span className={`swatch ${r.key}`} aria-hidden="true" />
          {r.label}
        </li>
      ))}
    </ul>
  );
}
