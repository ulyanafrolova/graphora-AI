import cytoscape, {
  type Core,
  type ElementDefinition,
  type LayoutOptions,
  type NodeCollection,
  type NodeSingular,
  type StylesheetJson,
} from "cytoscape";
import fcose from "cytoscape-fcose";
import svg from "cytoscape-svg";
import { packSiblings } from "d3-hierarchy";

import { STYLE } from "./style";

cytoscape.use(fcose);
cytoscape.use(svg);

export const WEBGL_FROM = 1000;
export const GRID_FROM = 500;

const BIG_STYLE: StylesheetJson = [
  ...STYLE,
  { selector: "edge", style: { "curve-style": "haystack", "target-arrow-shape": "none" } },
  { selector: "node", style: { "min-zoomed-font-size": 10 } },
];

export function createGraph(container: HTMLElement, webgl = false): Core {
  const options = {
    container,
    style: STYLE,
    minZoom: 0.05,
    maxZoom: 4,
    ...(webgl ? { renderer: { name: "canvas", webgl: true } } : {}),
  };
  const cy = cytoscape(options as cytoscape.CytoscapeOptions);
  (container as unknown as { cy: Core }).cy = cy;
  cy.on("zoom", () => scaleClusterLabels(cy));
  return cy;
}

/** Same picture on every load: start from a circle in node-id order, then fcose without randomising.
 * With `clusters` (the file level) files are laid out as clusters of their component instead, see clusterLayout. */
export function placeAndLayout(cy: Core, elements: ElementDefinition[], onDone: () => void, clusters = false): void {
  cy.elements().remove();
  cy.add(elements);
  const leaves = cy
    .nodes()
    .filter((n) => n.isChildless())
    .sort((a, b) => (a.id() < b.id() ? -1 : 1));
  const r = 60 + leaves.length * 12;
  leaves.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(leaves.length, 1);
    n.position({ x: r * Math.cos(angle), y: r * Math.sin(angle) });
  });
  const big = leaves.length > WEBGL_FROM;
  const finish = () => {
    cy.resize();
    cy.style(big ? BIG_STYLE : STYLE); // a fresh stylesheet after the elements exist; the first one leaves edges undrawn
    refit(cy);
    scaleClusterLabels(cy);
    onDone();
  };
  if (clusters) {
    clusterLayout(cy, leaves);
    finish();
    return;
  }
  if (leaves.length > GRID_FROM) {
    gridAndRing(leaves);
    finish();
    return;
  }
  cy.nodes().boundingBox(); // label sizes are measured lazily; fcose needs them to keep nodes apart
  const layout = cy.layout({
    name: "fcose",
    randomize: false,
    animate: false,
    quality: "default",
    nodeRepulsion: 9000,
    idealEdgeLength: 120,
    nodeSeparation: 90,
    packComponents: true,
    nodeDimensionsIncludeLabels: true,
  } as LayoutOptions);
  layout.one("layoutstop", finish);
  layout.run();
}

/** fcose takes about a minute on 1,500 files; files go on a grid in id order, collapsed components on a ring around it. */
function gridAndRing(leaves: NodeCollection): void {
  const inside = leaves.filter((n) => n.parent().nonempty());
  const grid = inside.nonempty() ? inside : leaves;
  const cols = Math.ceil(Math.sqrt(grid.length));
  grid.forEach((n, i) => {
    n.position({ x: (i % cols) * 160, y: Math.floor(i / cols) * 60 });
  });
  const ring = leaves.filter((n) => !grid.contains(n));
  const middle = { x: ((cols - 1) * 160) / 2, y: ((Math.ceil(grid.length / cols) - 1) * 60) / 2 };
  const r = Math.hypot(middle.x, middle.y) + 300;
  ring.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / ring.length - Math.PI / 2;
    n.position({ x: middle.x + r * Math.cos(angle), y: middle.y + r * Math.sin(angle) });
  });
}

/** cy.fit measures every label and edge; leaf positions are enough to frame the graph. */
function fitLeaves(cy: Core, leaves: NodeCollection): void {
  if (leaves.empty()) return;
  let [x1, y1, x2, y2] = [Infinity, Infinity, -Infinity, -Infinity];
  leaves.forEach((n) => {
    const { x, y } = n.position();
    [x1, y1, x2, y2] = [Math.min(x1, x), Math.min(y1, y), Math.max(x2, x), Math.max(y2, y)];
  });
  const pad = 120;
  const zoom = Math.min(1.5, cy.width() / (x2 - x1 + 2 * pad), cy.height() / (y2 - y1 + 2 * pad));
  cy.viewport({
    zoom,
    pan: { x: cy.width() / 2 - (zoom * (x1 + x2)) / 2, y: cy.height() / 2 - (zoom * (y1 + y2)) / 2 },
  });
}

const SPACING = 34; // between neighbouring dots inside a cluster
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

/** Files of one component close together, components with many links between them close to each other.
 * The clusters are discs sized by their file count, packed together; the files of a cluster then fill its
 * disc on a sunflower spiral, the most-imported in the middle. Deterministic and fast for thousands of files:
 * no force layout runs. */
function clusterLayout(cy: Core, leaves: NodeCollection): void {
  const groups = new Map<string, NodeSingular[]>();
  leaves.forEach((n) => {
    const key = String(n.data("group") ?? "~");
    const list = groups.get(key) ?? [];
    list.push(n);
    groups.set(key, list);
  });
  const keys = [...groups.keys()].sort();
  // the spiral of n dots reaches 0.9 · SPACING · √n; plus half the biggest dot
  const radius = new Map(keys.map((k) => [k, 0.9 * SPACING * Math.sqrt(groups.get(k)?.length ?? 1) + 14]));
  const weight = new Map<string, number>();
  cy.edges().forEach((e) => {
    const a = String(e.source().data("group") ?? "~");
    const b = String(e.target().data("group") ?? "~");
    if (a === b) return;
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    weight.set(key, (weight.get(key) ?? 0) + 1);
  });
  const centers = placeGroups(keys, radius, weight);
  for (const key of keys) {
    const members = (groups.get(key) ?? []).sort(
      (a, b) => Number(b.data("size") ?? 0) - Number(a.data("size") ?? 0) || (a.id() < b.id() ? -1 : 1),
    );
    const c = centers.get(key) ?? { x: 0, y: 0 };
    members.forEach((n, k) => {
      const r = SPACING * Math.sqrt(k + 0.5) * 0.9;
      n.position({ x: c.x + r * Math.cos(k * GOLDEN), y: c.y + r * Math.sin(k * GOLDEN) });
    });
  }
}

/** Cluster discs packed tightly (d3 packSiblings): the biggest first, then always the cluster with the most links
 * to those already placed, so connected components end up side by side. */
function placeGroups(
  keys: string[],
  radius: Map<string, number>,
  weight: Map<string, number>,
): Map<string, { x: number; y: number }> {
  const link = (a: string, b: string) => weight.get(a < b ? `${a}|${b}` : `${b}|${a}`) ?? 0;
  const left = [...keys].sort((a, b) => (radius.get(b) ?? 0) - (radius.get(a) ?? 0) || (a < b ? -1 : 1));
  const order: string[] = [];
  while (left.length) {
    let best = 0;
    let score = -1;
    left.forEach((k, i) => {
      const s = order.reduce((n, o) => n + link(k, o), 0);
      if (s > score) [best, score] = [i, s];
    });
    order.push(...left.splice(best, 1));
  }
  const circles = order.map((k) => ({ key: k, r: (radius.get(k) ?? 40) + 18, x: 0, y: 0 })); // room for the label
  packSiblings(circles);
  return new Map(circles.map((c) => [c.key, { x: c.x, y: c.y }]));
}

/** Cluster names keep about the same size on screen at any zoom, so the map stays readable zoomed out; a name
 * that would cover a bigger cluster's name waits until the view is zoomed in enough to make room. */
function scaleClusterLabels(cy: Core): void {
  const clusters = cy.nodes(".cluster");
  if (clusters.empty()) return;
  const k = 1 / Math.max(cy.zoom(), 0.05);
  const taken: { x1: number; x2: number; y1: number; y2: number }[] = [];
  const bySize = clusters.sort((a, b) => b.children().length - a.children().length || (a.id() < b.id() ? -1 : 1));
  // decide first: inside cy.batch the boxes of compound nodes are not brought up to date
  const shown = bySize.map((c) => {
    const box = c.renderedBoundingBox({ includeLabels: false });
    const w = String(c.data("label") ?? "").length * 7.5 + 16; // 13px bold text plus padding, in screen pixels
    const middle = (box.x1 + box.x2) / 2;
    const label = { x1: middle - w / 2, x2: middle + w / 2, y1: box.y1 - 4, y2: box.y1 + 26 };
    const free = !taken.some((t) => t.x1 < label.x2 && label.x1 < t.x2 && t.y1 < label.y2 && label.y1 < t.y2);
    if (free) taken.push(label);
    return free;
  });
  cy.batch(() => {
    bySize.forEach((c, i) => {
      const on = shown[i] ? 1 : 0;
      c.style({
        "font-size": Math.min(13 * k, 80),
        "text-background-padding": `${Math.min(5 * k, 30)}px`,
        "text-margin-y": 10 * k,
        "text-opacity": on,
        "text-background-opacity": on,
        "text-border-opacity": on,
      });
    });
  });
}

/** The whole graph in view, never zoomed in past 1.5×: after a layout and whenever the canvas changes size. */
export function refit(cy: Core): void {
  const leaves = cy.nodes().filter((n) => n.isChildless());
  if (leaves.empty()) return;
  if (leaves.length > GRID_FROM) {
    fitLeaves(cy, leaves);
    return;
  }
  cy.fit(undefined, 24);
  if (cy.zoom() > 1.5) {
    cy.zoom(1.5);
    cy.center();
  }
}
