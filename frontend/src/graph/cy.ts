import cytoscape, { type Core, type ElementDefinition, type LayoutOptions } from "cytoscape";
import fcose from "cytoscape-fcose";
import svg from "cytoscape-svg";

import { STYLE } from "./style";

cytoscape.use(fcose);
cytoscape.use(svg);

export const WEBGL_FROM = 1000;
export const WORKER_FROM = 500;

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
  const finish = () => {
    cy.resize();
    cy.style(STYLE); // a fresh stylesheet after the elements exist; the first one leaves edges undrawn
    if (leaves.length > WEBGL_FROM) {
      cy.edges().style({ "curve-style": "haystack", "target-arrow-shape": "none" });
      cy.nodes().style({ "min-zoomed-font-size": 10 });
    }
    cy.fit(undefined, 40);
    if (cy.zoom() > 1.5) {
      cy.zoom(1.5);
      cy.center();
    }
    onDone();
  };
  if (leaves.length > WORKER_FROM && typeof Worker !== "undefined") {
    const worker = new Worker(new URL("./layout.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<Record<string, { x: number; y: number }>>) => {
      worker.terminate();
      cy.nodes().forEach((n) => {
        const p = event.data[n.id()];
        if (p && n.isChildless()) n.position(p);
      });
      finish();
    };
    worker.postMessage({ elements: cy.elements().jsons() });
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
