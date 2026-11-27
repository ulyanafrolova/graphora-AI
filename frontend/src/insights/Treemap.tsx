import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";
import { useLayoutEffect, useMemo, useRef, useState } from "react";

import type { History, Item } from "@/api/types";
import { nodeName, splitPath } from "@/graph/names";

const STOPS: [number, [number, number, number]][] = [
  [0, [0x1f, 0x3d, 0x2b]],
  [0.5, [0xd2, 0x99, 0x22]],
  [1, [0xda, 0x36, 0x33]],
];

export function riskColor(score: number, max: number): string {
  const t = max > 0 ? Math.min(1, Math.max(0, score / max)) : 0;
  const [lo, hi] = t <= 0.5 ? [STOPS[0], STOPS[1]] : [STOPS[1], STOPS[2]];
  if (lo === undefined || hi === undefined) return "#888888";
  const k = (t - lo[0]) / (hi[0] - lo[0]);
  return `#${lo[1]
    .map((v, j) =>
      Math.round(v + ((hi[1][j] ?? v) - v) * k)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

export interface Tile {
  node: string;
  score: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  color: string;
}

export function tiles(items: Item[], lines: Map<string, number>, width: number, height: number): Tile[] {
  const sorted = [...items].sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || (a.node < b.node ? -1 : 1));
  const total = sorted.reduce((n, i) => n + (lines.get(nodeName(i.node)) ?? 0), 0);
  const floor = Math.max(1, total * 0.02);
  const max = sorted[0]?.score ?? 0;
  const root = hierarchy<{ item?: Item; children?: { item: Item }[] }>({ children: sorted.map((item) => ({ item })) })
    .sum((d) => (d.item ? Math.max(lines.get(nodeName(d.item.node)) ?? 0, floor) : 0))
    .sort((a, b) => (b.data.item?.score ?? 0) - (a.data.item?.score ?? 0));
  treemap<{ item?: Item }>().tile(treemapSquarify).size([width, height]).paddingInner(3)(root);
  return root.leaves().flatMap((leaf) => {
    const l = leaf as typeof leaf & { x0: number; y0: number; x1: number; y1: number };
    const item = leaf.data.item;
    if (item === undefined) return [];
    return {
      node: item.node,
      score: item.score ?? 0,
      x0: l.x0,
      y0: l.y0,
      x1: l.x1,
      y1: l.y1,
      color: riskColor(item.score ?? 0, max),
    };
  });
}

const day = (stamp: string | null) => (stamp ?? "").slice(0, 10);

export function historyLine(h: History): string {
  if (h.status === "not_available")
    return `history not available (${h.reason === "skipped" ? "skipped by request" : h.reason})`;
  let line =
    h.status === "partial"
      ? `partial history (time limit): ${h.commits_read} commits read back to ${day(h.oldest)}`
      : `${h.commits_read} commits from ${day(h.oldest)} to ${day(h.newest)} (window from ${day(h.window_start)})`;
  if (h.merges_skipped) line += `, ${h.merges_skipped} merges not counted`;
  if (h.local_changes) line += "; uncommitted changes not counted";
  if (h.shallow_skipped) line += `; ${h.shallow_skipped} commits not counted (shallow history)`;
  return line;
}

/** Which labels a tile of this size can hold without cutting them to a few letters. */
export function tileLabels(width: number, height: number): { name: boolean; score: boolean } {
  const name = width >= 52 && height >= 24;
  return { name, score: name && width >= 78 && height >= 46 };
}

/** Map height for a given width: wide enough to read, never a thin strip or a tower. */
export const mapHeight = (width: number) => Math.round(Math.min(560, Math.max(280, width * 0.62)));

export function Treemap({
  items,
  lines,
  onOpen,
}: {
  items: Item[];
  lines: Map<string, number>;
  onOpen: (node: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  // laid out in real pixels of the box, so a label is shown only where it fits; 900 until measured (and in tests)
  const [width, setWidth] = useState(900);
  useLayoutEffect(() => {
    const el = box.current;
    if (el === null) return;
    const measure = () => {
      if (el.clientWidth > 0) setWidth(el.clientWidth);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const height = mapHeight(width);
  const laid = useMemo(() => tiles(items, lines, width, height), [items, lines, width, height]);
  return (
    <div className="treemap" ref={box} style={{ height }}>
      {laid.map((t) => {
        const w = t.x1 - t.x0;
        const h = t.y1 - t.y0;
        const show = tileLabels(w, h);
        return (
          <button
            key={t.node}
            type="button"
            className="tile"
            title={`${nodeName(t.node)} · score ${t.score}`}
            aria-label={`${nodeName(t.node)}, score ${t.score}`}
            onClick={() => onOpen(t.node)}
            style={{ left: t.x0, top: t.y0, width: w, height: h, background: t.color }}
          >
            {show.name && (
              <span className="tile-label">
                <span className="name">{splitPath(nodeName(t.node)).name}</span>
                {show.score && <span className="score">score {t.score}</span>}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
