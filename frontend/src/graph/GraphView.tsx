import type { Core, NodeSingular } from "cytoscape";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { download, Minimap } from "./Minimap";
import { createGraph, placeAndLayout, refit, WEBGL_FROM } from "./cy";
import { toElements } from "./elements";
import { COLOR } from "./style";

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

/** The node, its neighbours and their links stand out; everything else fades. null clears the focus. */
function focus(g: Core, node: NodeSingular | null): void {
  g.batch(() => {
    g.elements().removeClass("focus faded");
    if (node === null || node.empty() || node.data("kind") === "cluster") return;
    const hood = node.closedNeighborhood();
    hood.addClass("focus");
    g.elements().not(hood).addClass("faded");
  });
}

const MINIMAP_FROM = 150;

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
  const view = useRef<HTMLElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const changed = () => setFull(document.fullscreenElement === view.current);
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);
  const toggleFull = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void view.current?.requestFullscreen();
  };
  // the selection keeps its neighbourhood in focus, except in impact mode, which paints its own
  const focused = route.impact ? null : route.node;
  const handlers = useRef({ onChange, level, focused });
  useLayoutEffect(() => {
    handlers.current = { onChange, level, focused };
  });

  useEffect(() => {
    if (box.current === null) return;
    const g = createGraph(box.current, webgl);
    cy.current = g;
    setInstance(g);
    // a new canvas size (window, side panel, full screen) fits the graph again instead of leaving it off-centre
    let frame = 0;
    let last = { w: box.current.clientWidth, h: box.current.clientHeight };
    const resize = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const el = box.current;
        if (el === null || (el.clientWidth === last.w && el.clientHeight === last.h)) return;
        last = { w: el.clientWidth, h: el.clientHeight };
        g.resize();
        refit(g);
      });
    });
    resize.observe(box.current);
    g.on("tap", "node", (event) => {
      const id = event.target.id() as string;
      const kind = event.target.data("kind") as string;
      const { onChange: change, level: current } = handlers.current;
      if (kind === "component") {
        if (current === "component" && event.target.isParent()) return;
        change(current === "system" ? { node: id } : { level: "component", component: id, node: null });
      } else if (kind === "cluster") {
        const component = event.target.data("component") as string | undefined;
        if (component !== undefined) change({ node: component });
      } else {
        change({ node: id });
      }
    });
    g.on("tap", (event) => {
      if (event.target === g) handlers.current.onChange({ node: null, impact: false });
    });
    const selection = () => {
      const id = handlers.current.focused;
      return id === null ? null : g.getElementById(id);
    };
    g.on("mouseover", "node", (event) => focus(g, event.target as NodeSingular));
    g.on("mouseout", "node", () => focus(g, selection()));
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      g.destroy();
      cy.current = null;
    };
  }, [webgl]);

  useEffect(() => {
    const g = cy.current;
    if (g === null) return;
    setReady(false);
    placeAndLayout(
      g,
      elements,
      () => {
        setCounts([g.nodes().length, g.edges().length]);
        setReady(true);
      },
      level === "file",
    );
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
        if (el.isNode() && e.data.major !== undefined) el.data({ major: e.data.major });
      }
    }
    focus(g, focused === null ? null : g.getElementById(focused));
  }, [elements, focused, ready]);

  const shown = component === null ? 0 : component.files.length;
  return (
    <section className="graph-view" ref={view}>
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
      <div className="canvas-wrap">
        <div
          className="canvas"
          ref={box}
          data-ready={ready ? "true" : "false"}
          data-nodes={counts[0]}
          data-edges={counts[1]}
          data-testid="graph"
        />
        {/* over the canvas it would hide part of a small graph, which fits the view anyway */}
        {(counts[0] ?? 0) > MINIMAP_FROM && <Minimap cy={instance} ready={ready} />}
      </div>
      <div className="graph-tools">
        <button type="button" aria-pressed={full} onClick={toggleFull}>
          {full ? "Exit full screen" : "Full screen"}
        </button>
        <button
          type="button"
          onClick={() => cy.current && download("graph.png", cy.current.png({ full: true, bg: COLOR.bg }))}
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
                `data:image/svg+xml;charset=utf-8,${encodeURIComponent(g.svg({ full: true, bg: COLOR.bg }))}`,
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
