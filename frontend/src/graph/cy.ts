import cytoscape, {
  type Core,
  type ElementDefinition,
  type LayoutOptions,
  type NodeCollection,
  type StylesheetJson,
} from "cytoscape";
import fcose from "cytoscape-fcose";
import svg from "cytoscape-svg";

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
  return cy;
}

/** Same picture on every load: start from a circle in node-id order, then fcose without randomising. */
export function placeAndLayout(cy: Core, elements: ElementDefinition[], onDone: () => void): void {
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
    fitLeaves(cy, leaves);
    onDone();
  };
  if (leaves.length > GRID_FROM) {
    gridAndRing(leaves);
    finish();
    return;
  }
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
