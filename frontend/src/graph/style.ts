import type { StylesheetJson } from "cytoscape";

// The same values as src/styles/tokens.css; Cytoscape cannot read CSS variables.
export const PALETTE = [
  "#58a6ff",
  "#3fb950",
  "#a371f7",
  "#db6d28",
  "#db61a2",
  "#d29922",
  "#8b949e",
  "#39c5cf",
  "#f0883e",
  "#7ee787",
  "#d2a8ff",
  "#ffa198",
  "#79c0ff",
  "#e3b341",
];
export const COLOR = {
  bg: "#0b0e14", // --bg in styles/tokens.css: the background of exported and minimap images
  text: "#e6edf3",
  muted: "#8b949e",
  edge: "#4b5563",
  panel: "#12161e",
  heuristic: "#d29922",
  cycle: "#f85149",
  impact: "#58a6ff",
  selected: "#a371f7",
};

export function paletteColor(index: number): string {
  return index > 0 ? (PALETTE[(index - 1) % PALETTE.length] ?? COLOR.muted) : COLOR.muted;
}

export const STYLE: StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      color: COLOR.text,
      "font-size": 12,
      "font-family": "SF Mono, Menlo, monospace",
      "text-valign": "bottom",
      "text-margin-y": 6,
      "background-color": COLOR.panel,
      "border-width": 2,
      "border-color": COLOR.muted,
    },
  },
  {
    selector: "node.component",
    style: {
      shape: "ellipse",
      width: "mapData(deps, 0, 400, 46, 150)",
      height: "mapData(deps, 0, 400, 46, 150)",
      label: "data(caption)",
      "text-wrap": "wrap",
      "font-size": 15,
      "font-weight": "bold",
      "font-family": "-apple-system, Inter, sans-serif",
    },
  },
  {
    selector: "node.expanded",
    style: { shape: "round-rectangle", "border-style": "dashed", "text-valign": "top", "text-margin-y": -6 },
  },
  {
    selector: "node.file",
    style: {
      shape: "round-rectangle",
      width: "label",
      height: 26,
      padding: "6px",
      "text-valign": "center",
      "text-margin-y": 0,
    },
  },
  {
    selector: "node.external",
    style: {
      shape: "round-rectangle",
      width: "label",
      height: 22,
      padding: "4px",
      "border-style": "dotted",
      color: COLOR.muted,
      "text-valign": "center",
      "text-margin-y": 0,
    },
  },
  { selector: "node.selected", style: { "border-color": COLOR.selected, "border-width": 4 } },
  { selector: "node.impacted", style: { "border-color": COLOR.impact, "border-width": 3 } },
  { selector: "node.dimmed", style: { opacity: 0.35 } },
  {
    selector: "edge",
    style: {
      width: "mapData(imports, 1, 30, 1.5, 8)",
      "line-color": COLOR.edge,
      "target-arrow-color": COLOR.edge,
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,
      "curve-style": "bezier",
      opacity: 0.85,
    },
  },
  { selector: "edge.type-only", style: { "line-style": "dotted" } },
  {
    selector: "edge.heuristic",
    style: { "line-style": "dashed", "line-color": COLOR.heuristic, "target-arrow-color": COLOR.heuristic },
  },
  { selector: "edge.cycle", style: { "line-color": COLOR.cycle, "target-arrow-color": COLOR.cycle } },
  {
    selector: "edge.impact",
    style: { "line-color": COLOR.impact, "target-arrow-color": COLOR.impact, width: 3, opacity: 1 },
  },
  { selector: "edge.dimmed", style: { opacity: 0.12 } },
];

for (let i = 1; i <= PALETTE.length; i++) {
  STYLE.push({ selector: `node[color = ${i}]`, style: { "border-color": paletteColor(i) } });
  STYLE.push({
    selector: `node.component[color = ${i}]`,
    style: { "background-color": paletteColor(i), "background-opacity": 0.12, "border-color": paletteColor(i) },
  });
}
STYLE.push({
  selector: "node.hotspot",
  style: {
    "underlay-color": COLOR.cycle,
    "underlay-opacity": 0.35,
    "underlay-padding": 8,
    "underlay-shape": "ellipse",
  },
});
STYLE.push({ selector: "node.selected", style: { "border-color": COLOR.selected, "border-width": 4 } });
STYLE.push({ selector: "node.impacted", style: { "border-color": COLOR.impact, "border-width": 3 } });
