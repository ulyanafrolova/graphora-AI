import type { Core } from "cytoscape";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { download, Minimap } from "./Minimap";
import { createGraph, placeAndLayout, WEBGL_FROM } from "./cy";
import { toElements } from "./elements";

import type { Answer, GraphDocument } from "@/api/types";
import { Legend } from "@/shell/Legend";
import { HIDDEN, type Hidden, type Level, type RouteState } from "@/state/route";

export interface GraphViewProps {
  route: RouteState;
  graph: GraphDocument;
  components: Answer;
  impact: Set<string> | null;
  cycles?: Answer | undefined;
  hot?: Set<string>;
  onChange: (next: Partial<RouteState>) => void;
  search?: React.ReactNode;
}

const LEVEL_LABELS: [Level, string][] = [
  ["system", "System"],
  ["component", "Component"],
  ["file", "File"],
];

export function GraphView({ route, graph, components, impact, cycles, hot, onChange, search }: GraphViewProps) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [instance, setInstance] = useState<Core | null>(null);
  const [ready, setReady] = useState(false);
  const [counts, setCounts] = useState([0, 0]);
  const comps = components.components ?? [];
  const component = comps.find((c) => c.id === route.component) ?? null;
  const level: Level = route.level === "component" && component === null ? "system" : route.level;

  const elements = useMemo(
    () =>
      toElements({
        level,
        component: route.component,
        components,
        graph,
        hide: route.hide,
        selected: route.node,
        impact,
        ...(cycles ? { cycles } : {}),
        ...(hot ? { hot } : {}),
      }),
    [level, route.component, components, graph, route.hide, route.node, impact, cycles, hot],
  );
  const structure = useMemo(() => elements.map((e) => e.data.id).join("|"), [elements]);
  const webgl = level === "file" && (components.components?.reduce((n, c) => n + c.file_count, 0) ?? 0) > WEBGL_FROM;
  const handlers = useRef({ onChange, level });
  useLayoutEffect(() => {
    handlers.current = { onChange, level };
  });

  useEffect(() => {
    if (box.current === null) return;
    const g = createGraph(box.current, webgl);
    cy.current = g;
    setInstance(g);
    const resize = new ResizeObserver(() => g.resize());
    resize.observe(box.current);
    g.on("tap", "node", (event) => {
      const id = event.target.id() as string;
      const kind = event.target.data("kind") as string;
      const { onChange: change, level: current } = handlers.current;
      if (kind === "component") {
        if (current === "component" && event.target.isParent()) return;
        change(current === "system" ? { node: id } : { level: "component", component: id, node: null });
      } else {
        change({ node: id });
      }
    });
    g.on("tap", (event) => {
      if (event.target === g) handlers.current.onChange({ node: null, impact: false });
    });
    return () => {
      resize.disconnect();
      g.destroy();
      cy.current = null;
    };
  }, [webgl]);

  useEffect(() => {
    const g = cy.current;
    if (g === null) return;
    setReady(false);
    placeAndLayout(g, elements, () => {
      setCounts([g.nodes().length, g.edges().length]);
      setReady(true);
    });
    // classes are refreshed below; the layout runs only when the set of elements changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure]);

  useEffect(() => {
    const g = cy.current;
    if (g === null) return;
    for (const e of elements) {
      const el = g.getElementById(e.data.id ?? "");
      if (el.nonempty()) {
        el.classes(e.classes ?? "");
        if (el.isNode() && e.data.caption !== undefined)
          el.data({ impacted: e.data.impacted, caption: e.data.caption });
      }
    }
  }, [elements]);

  const shown = component === null ? 0 : component.files.length;
  return (
    <section className="graph-view">
      <div className="toolbar">
        {search}
        <div className="tabs" role="tablist">
          {LEVEL_LABELS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={level === value}
              disabled={value === "component" && component === null}
              onClick={() => onChange({ level: value })}
            >
              {label}
            </button>
          ))}
        </div>
        {HIDDEN.map((h: Hidden) => (
          <label key={h} className="toggle">
            <input
              type="checkbox"
              checked={route.hide.includes(h)}
              onChange={(e) =>
                onChange({ hide: e.target.checked ? [...route.hide, h].sort() : route.hide.filter((x) => x !== h) })
              }
            />
            Hide {h === "tests" ? "tests" : "external"}
          </label>
        ))}
      </div>
      <div
        className="canvas"
        ref={box}
        data-ready={ready ? "true" : "false"}
        data-nodes={counts[0]}
        data-edges={counts[1]}
        data-testid="graph"
      />
      <div className="graph-tools">
        <Minimap cy={instance} ready={ready} />
        <button
          type="button"
          onClick={() => cy.current && download("graph.png", cy.current.png({ full: true, bg: "#0b0e14" }))}
        >
          Export PNG
        </button>
        <button
          type="button"
          onClick={() => {
            const g = cy.current as (Core & { svg: (o: object) => string }) | null;
            if (g)
              download(
                "graph.svg",
                `data:image/svg+xml;charset=utf-8,${encodeURIComponent(g.svg({ full: true, bg: "#0b0e14" }))}`,
              );
          }}
        >
          Export SVG
        </button>
      </div>
      <footer className="graph-footer">
        <span className="crumbs">
          <button type="button" className="link" onClick={() => onChange({ level: "system", component: null })}>
            System
          </button>
          {component !== null && (
            <>
              {" › "}
              <span className="accent">{component.name}</span> ({shown} of {component.file_count} files shown)
            </>
          )}
          {" · "}
          {comps.length} components
        </span>
        <Legend only={["resolved", "heuristic", "cycle", "impact"]} />
      </footer>
    </section>
  );
}
