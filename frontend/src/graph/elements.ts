// Answers of the service turned into Cytoscape elements: a view only, no graph walking (research R2).
import type { ElementDefinition } from "cytoscape";

import { componentLabel } from "./names";

import type { Answer, Component, GraphDocument } from "@/api/types";
import type { Hidden, Level } from "@/state/route";


export interface ElementsInput {
  level: Level;
  component: string | null;
  components: Answer;
  graph: GraphDocument;
  hide: Hidden[];
  selected: string | null;
  impact: Set<string> | null;
  cycles?: Answer;
  hot?: Set<string>;
}

const TEST = /(^|\/)(tests?|__tests__)\/|(_test|\.test|\.spec)\./;

export function isTest(path: string): boolean {
  return TEST.test(path);
}

interface Pair {
  source: string;
  target: string;
  imports: number;
  resolved: boolean;
  typeOnly: boolean;
}

function filePairs(graph: GraphDocument): Pair[] {
  const pairs = new Map<string, Pair>();
  for (const e of graph.edges) {
    if (e.confidence === "unresolved" || !e.source.startsWith("file:") || e.target.startsWith("unresolved:")) continue;
    const key = `${e.source}->${e.target}`;
    const pair = pairs.get(key) ?? { source: e.source, target: e.target, imports: 0, resolved: false, typeOnly: true };
    pair.imports += 1;
    pair.resolved ||= e.confidence === "resolved";
    pair.typeOnly &&= e.type_only;
    pairs.set(key, pair);
  }
  return [...pairs.values()].sort((a, b) =>
    a.source === b.source ? cmp(a.target, b.target) : cmp(a.source, b.source),
  );
}

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
const label = (id: string) => id.slice(id.lastIndexOf("/") + 1).replace(/^(file|ext:[a-z]+):/, "");
const caption = (c: Component, impacted?: number) =>
  `${componentLabel(c.name)}\n${c.file_count} ${c.file_count === 1 ? "file" : "files"}${impacted ? `\n${impacted} affected` : ""}`;
const classes = (...names: (string | false)[]) => names.filter(Boolean).join(" ");

export function toElements(input: ElementsInput): ElementDefinition[] {
  const comps = input.components.components ?? [];
  const where = new Map<string, number>();
  comps.forEach((c, i) => c.files.forEach((f) => where.set(f, i)));
  const loop = new Map<string, number>();
  (input.cycles?.groups ?? []).forEach((g, i) => g.files.forEach((f) => loop.set(f, i)));
  const inLoop = (a: string, b: string) => loop.has(a) && loop.get(a) === loop.get(b);
  const hideTests = input.hide.includes("tests");
  const hideExternal = input.hide.includes("external");
  const shownFile = (id: string) => !(hideTests && isTest(id.replace(/^file:/, "")));
  const els: ElementDefinition[] = [];

  const node = (id: string, data: Record<string, unknown>, cls: string, holds: string[] = []) => {
    const selected = input.selected === id || (input.selected !== null && holds.includes(input.selected));
    const impacted = (input.impact?.has(id) ?? false) || holds.some((f) => input.impact?.has(f));
    els.push({
      data: { id, ...data },
      classes: classes(
        cls,
        selected && "selected",
        impacted && "impacted",
        input.impact !== null && !selected && !impacted && !cls.includes("expanded") && "dimmed",
      ),
    });
  };
  const edge = (source: string, target: string, data: Record<string, unknown>, cls: string) => {
    const on = (id: string) => input.selected === id || (input.impact?.has(id) ?? false);
    const lit = input.impact !== null && on(source) && on(target);
    els.push({
      data: { id: `${source}->${target}`, source, target, ...data },
      classes: classes(cls, lit && "impact", input.impact !== null && !lit && "dimmed"),
    });
  };
  const componentNode = (c: Component, i: number, expanded: boolean) => {
    const impacted =
      input.impact === null || expanded ? {} : { impacted: c.files.filter((f) => input.impact?.has(f)).length };
    node(
      c.id,
      {
        label: componentLabel(c.name),
        caption: caption(c, impacted.impacted),
        count: c.file_count,
        color: i + 1,
        kind: "component",
        deps: (input.components.links ?? []).filter((l) => l.target === c.id).reduce((n, l) => n + l.imports, 0),
        ...impacted,
      },
      classes(
        "component",
        c.has_cycle && "cycle",
        expanded && "expanded",
        c.files.some((f) => input.hot?.has(f)) && "hotspot",
      ),
      expanded ? [] : c.files,
    );
  };

  if (input.level === "system") {
    comps.forEach((c, i) => componentNode(c, i, false));
    for (const l of input.components.links ?? []) {
      edge(
        l.source,
        l.target,
        { imports: l.imports },
        classes("link", l.heuristic > 0 && "heuristic", l.in_cycle && "cycle"),
      );
    }
    return els;
  }

  if (input.level === "component") {
    const open = comps.findIndex((c) => c.id === input.component);
    comps.forEach((c, i) => {
      componentNode(c, i, i === open);
      if (i !== open) return;
      for (const f of c.files.filter(shownFile))
        node(f, { label: label(f), parent: c.id, color: i + 1, kind: "file" }, "file");
    });
    if (open < 0) return els;
    const inside = new Set(comps[open]?.files.filter(shownFile));
    const out = new Map<string, { imports: number; heuristic: boolean }>();
    for (const p of filePairs(input.graph)) {
      if (!inside.has(p.source)) continue;
      if (inside.has(p.target)) {
        edge(
          p.source,
          p.target,
          { imports: p.imports },
          classes("link", !p.resolved && "heuristic", p.typeOnly && "type-only", inLoop(p.source, p.target) && "cycle"),
        );
        continue;
      }
      const target = where.get(p.target);
      if (target === undefined || target === open) continue;
      const key = `${p.source}->${comps[target]?.id ?? ""}`;
      const agg = out.get(key) ?? { imports: 0, heuristic: false };
      agg.imports += p.imports;
      agg.heuristic ||= !p.resolved;
      out.set(key, agg);
    }
    for (const [key, agg] of out) {
      const [source = "", target = ""] = key.split("->");
      edge(source, target, { imports: agg.imports }, classes("link", agg.heuristic && "heuristic"));
    }
    const openId = comps[open]?.id;
    for (const l of input.components.links ?? []) {
      if (l.source === openId) continue;
      edge(
        l.source,
        l.target,
        { imports: l.imports },
        classes("link", l.heuristic > 0 && "heuristic", l.in_cycle && "cycle"),
      );
    }
    return els;
  }

  const files = input.graph.nodes
    .filter((n) => n.kind === "file")
    .map((n) => n.id)
    .filter(shownFile)
    .sort(cmp);
  const shown = new Set(files);
  const pairs = filePairs(input.graph).filter(
    (p) => shown.has(p.source) && (shown.has(p.target) || (p.target.startsWith("ext:") && !hideExternal)),
  );
  for (const f of files)
    node(
      f,
      { label: label(f), color: (where.get(f) ?? -1) + 1, kind: "file" },
      classes("file", input.hot?.has(f) === true && "hotspot"),
    );
  const externals = [...new Set(pairs.filter((p) => p.target.startsWith("ext:")).map((p) => p.target))].sort(cmp);
  for (const x of externals) node(x, { label: label(x), kind: "external" }, "external");
  for (const p of pairs) {
    edge(
      p.source,
      p.target,
      { imports: p.imports },
      classes(
        "link",
        !p.resolved && "heuristic",
        p.typeOnly && "type-only",
        p.target.startsWith("ext:") && "external",
        inLoop(p.source, p.target) && "cycle",
      ),
    );
  }
  return els;
}
