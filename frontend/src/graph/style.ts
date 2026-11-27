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

// File level: dots in clusters (elements.ts, clusterLayout in cy.ts)
const SANS = "-apple-system, Inter, Segoe UI, sans-serif";
STYLE.push(
  {
    selector: "node.cluster",
    style: {
      shape: "round-rectangle",
      padding: "22px",
      "background-opacity": 0,
      "border-width": 0,
      label: "data(label)",
      "text-valign": "top",
      "text-halign": "center",
      "text-margin-y": 10,
      color: COLOR.text,
      "font-family": SANS,
      "font-size": 13,
      "font-weight": "bold",
      "text-background-color": COLOR.panel,
      "text-background-opacity": 1,
      "text-background-padding": "5px",
      "text-background-shape": "roundrectangle",
      "text-border-width": 1,
      "text-border-opacity": 1,
      "min-zoomed-font-size": 0,
    },
  },
  {
    selector: "node.file[size], node.external[size]",
    style: {
      shape: "ellipse",
      width: "data(size)",
      height: "data(size)",
      padding: "0px",
      "border-width": 0,
      "background-opacity": 0.95,
      label: "data(label)",
      "text-valign": "bottom",
      "text-margin-y": 4,
      color: COLOR.muted,
      "font-family": SANS,
      "font-size": 11,
      "text-outline-color": COLOR.bg,
      "text-outline-width": 2,
      "min-zoomed-font-size": 13, // most labels appear only from about 1.3× zoom
    },
  },
  { selector: "node.external[size]", style: { "background-color": COLOR.muted, "background-opacity": 0.5 } },
  {
    selector: "node.external-cluster",
    style: { "background-color": COLOR.muted, "text-border-color": COLOR.muted, color: COLOR.muted },
  },
  {
    selector: "node.file[?major]",
    style: { color: COLOR.text, "font-size": 13, "font-weight": "bold", "min-zoomed-font-size": 6 },
  },
  {
    selector: "edge[?fine]",
    style: {
      width: 1,
      opacity: 0.22,
      "curve-style": "haystack",
      "haystack-radius": 0,
      "target-arrow-shape": "none",
    },
  },
  { selector: "edge[?fine][?cross]", style: { opacity: 0.1 } },
  { selector: "edge[?fine].external", style: { opacity: 0.03 } }, // shown on focus: the fan to packages hides the rest
  { selector: "edge[?fine].cycle", style: { opacity: 0.55 } },
  // hover or selection: the node, its neighbours and their links stand out, the rest fades
  { selector: "node.faded", style: { opacity: 0.15 } },
  { selector: "node.cluster.faded", style: { opacity: 1 } },
  { selector: "edge.faded", style: { opacity: 0.03 } },
  {
    selector: "node.focus",
    style: { color: COLOR.text, "min-zoomed-font-size": 0, "z-index": 10, opacity: 1 },
  },
  {
    selector: "edge.focus",
    style: {
      opacity: 0.95,
      width: 1.6,
      "curve-style": "straight",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.7,
      "z-index": 10,
    },
  },
);
for (let i = 1; i <= PALETTE.length; i++) {
  STYLE.push(
    {
      selector: `node.cluster[color = ${i}]`,
      style: { "background-color": paletteColor(i), "text-border-color": paletteColor(i) },
    },
    { selector: `node.file[size][color = ${i}]`, style: { "background-color": paletteColor(i) } },
    {
      selector: `edge[?fine][color = ${i}]`,
      style: { "line-color": paletteColor(i), "target-arrow-color": paletteColor(i) },
    },
  );
}
STYLE.push({ selector: "edge[?fine].cycle", style: { "line-color": COLOR.cycle, "target-arrow-color": COLOR.cycle } });
// impact mode keeps its look on the file level: these come after the faint links above
STYLE.push(
  {
    selector: "edge[?fine].impact",
    style: {
      "line-color": COLOR.impact,
      "target-arrow-color": COLOR.impact,
      opacity: 1,
      width: 2,
      "curve-style": "straight",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.7,
    },
  },
  { selector: "edge[?fine].dimmed", style: { opacity: 0.03 } },
);
STYLE.push({
  selector: "node.file[size].selected",
  style: { "border-width": 3, "border-color": COLOR.text, "min-zoomed-font-size": 0, color: COLOR.text },
});
STYLE.push({ selector: "node.file[size].impacted", style: { "border-width": 3, "border-color": COLOR.impact } });
// an open component shows its files; a glow around the whole box only blurs them
STYLE.push({ selector: "node.expanded.hotspot", style: { "underlay-opacity": 0 } });
STYLE.push({ selector: "node.selected", style: { "border-color": COLOR.selected, "border-width": 4 } });
STYLE.push({ selector: "node.impacted", style: { "border-color": COLOR.impact, "border-width": 3 } });
