import type { BoundingBox12, BoundingBoxWH, Core } from "cytoscape";
import { useEffect, useRef, useState } from "react";

interface Frame {
  image: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A picture of the whole graph with the visible part framed; clicking pans the main view there. */
export function Minimap({ cy, ready }: { cy: Core | null; ready: boolean }) {
  const [frame, setFrame] = useState<Frame | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const bounds = useRef<(BoundingBox12 & BoundingBoxWH) | null>(null);
  useEffect(() => {
    if (cy === null || !ready) return;
    const all = cy.nodes().boundingBox({ includeLabels: false });
    bounds.current = all;
    let image = "";
    const update = () => {
      const view = cy.extent();
      const w = Math.max(all.w, 1);
      const h = Math.max(all.h, 1);
      setFrame({ image, x: (view.x1 - all.x1) / w, y: (view.y1 - all.y1) / h, w: view.w / w, h: view.h / h });
    };
    // the picture waits until the main view has been drawn
    const later = window.setTimeout(() => {
      image = cy.png({ full: true, maxWidth: 240, maxHeight: 150, bg: "#0b0e14" });
      update();
    }, 300);
    update();
    cy.on("viewport", update);
    return () => {
      window.clearTimeout(later);
      cy.off("viewport", update);
    };
  }, [cy, ready]);
  // the box keeps its place before the picture exists, so the graph does not shrink after fitting
  if (frame === null) return <div className="minimap" aria-hidden="true" />;
  const pan = (e: React.MouseEvent) => {
    if (cy === null || box.current === null) return;
    const r = box.current.getBoundingClientRect();
    const all = bounds.current;
    if (all === null) return;
    const x = all.x1 + ((e.clientX - r.left) / r.width) * all.w;
    const y = all.y1 + ((e.clientY - r.top) / r.height) * all.h;
    cy.pan({ x: cy.width() / 2 - x * cy.zoom(), y: cy.height() / 2 - y * cy.zoom() });
  };
  const clamp = (v: number) => `${Math.min(100, Math.max(0, v * 100))}%`;
  return (
    <div className="minimap" ref={box} onClick={pan} data-testid="minimap" role="presentation">
      {frame.image !== "" && <img src={frame.image} alt="" />}
      <i style={{ left: clamp(frame.x), top: clamp(frame.y), width: clamp(frame.w), height: clamp(frame.h) }} />
    </div>
  );
}

export function download(name: string, href: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
}
