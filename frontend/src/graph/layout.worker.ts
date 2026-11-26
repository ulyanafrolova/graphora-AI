// fcose for big graphs off the main thread; positions only come back (research R11).
import cytoscape, { type ElementDefinition, type LayoutOptions } from "cytoscape";
import fcose from "cytoscape-fcose";

cytoscape.use(fcose);

self.onmessage = (event: MessageEvent<{ elements: ElementDefinition[] }>) => {
  const cy = cytoscape({ headless: true, styleEnabled: true, elements: event.data.elements });
  cy.layout({
    name: "fcose",
    randomize: false,
    animate: false,
    quality: "draft",
    packComponents: true,
    idealEdgeLength: 80,
  } as LayoutOptions).run();
  const positions: Record<string, { x: number; y: number }> = {};
  cy.nodes().forEach((n) => {
    if (n.isChildless()) positions[n.id()] = n.position();
  });
  self.postMessage(positions);
};
