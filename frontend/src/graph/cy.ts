import cytoscape, { type Core, type ElementDefinition, type LayoutOptions } from "cytoscape";
import fcose from "cytoscape-fcose";

import { STYLE } from "./style";

cytoscape.use(fcose);

export function createGraph(container: HTMLElement): Core {
  const cy = cytoscape({ container, style: STYLE, minZoom: 0.05, maxZoom: 4 });
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
  layout.one("layoutstop", () => {
    cy.resize();
    cy.style(STYLE); // a fresh stylesheet after the elements exist; the first one leaves edges undrawn
    cy.fit(undefined, 40);
    if (cy.zoom() > 1.5) {
      cy.zoom(1.5);
      cy.center();
    }
    onDone();
  });
  layout.run();
}
