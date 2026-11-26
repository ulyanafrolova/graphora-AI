import { useEffect, useState } from "react";

import { tokenize, type Token } from "./tokens";

import type { Edge, FileLines } from "@/api/types";

export type MarkerKind = "resolved" | "external" | "http" | "unresolved";
export interface Marker {
  kind: MarkerKind;
  edges: Edge[];
}

const LABELS: Record<MarkerKind, string> = {
  resolved: "resolved import",
  external: "external package",
  http: "HTTP route (bridge)",
  unresolved: "unresolved import",
};

export function lineMarkers(path: string, edges: Edge[]): Map<number, Marker> {
  const out = new Map<number, Marker>();
  for (const e of edges) {
    if (e.source !== `file:${path}`) continue;
    const kind: MarkerKind =
      e.type === "http_call"
        ? "http"
        : e.confidence === "unresolved"
          ? "unresolved"
          : e.target.startsWith("ext:")
            ? "external"
            : "resolved";
    const m = out.get(e.line);
    if (m) m.edges.push(e);
    else out.set(e.line, { kind, edges: [e] });
  }
  return new Map([...out.entries()].sort((a, b) => a[0] - b[0]));
}

export interface CodeViewProps {
  lines: FileLines | undefined;
  markers: Map<number, Marker>;
  selected: number | null;
  onSelect: (line: number) => void;
}

export function CodeView({ lines, markers, selected, onSelect }: CodeViewProps) {
  const [colored, setColored] = useState<{ for: FileLines; tokens: Token[][] | null } | null>(null);
  useEffect(() => {
    let live = true;
    if (lines?.has_text) {
      void tokenize(lines.path, lines.lines.map((l) => l.text).join("\n")).then((t) => {
        if (live) setColored({ for: lines, tokens: t });
      });
    }
    return () => {
      live = false;
    };
  }, [lines]);
  const tokens = colored !== null && colored.for === lines ? colored.tokens : null;

  if (lines === undefined) return null;
  if (!lines.has_text) return <p className="muted">Binary file: no text to show.</p>;
  return (
    <ol className="code mono">
      {lines.lines.map((l, i) => {
        const m = markers.get(l.n);
        return (
          <li
            key={l.n}
            data-testid={`line-${l.n}`}
            aria-current={selected === l.n ? "true" : undefined}
            className={m ? "marked" : ""}
            onClick={() => m && onSelect(l.n)}
          >
            <span className="gutter">{m && <i className={`marker ${m.kind}`} aria-label={LABELS[m.kind]} />}</span>
            <span className="n">{l.n}</span>
            <span className="text">
              {tokens?.[i]
                ? tokens[i]?.map((t, j) => (
                    <span key={j} style={t.color ? { color: t.color } : undefined}>
                      {t.content}
                    </span>
                  ))
                : l.text}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export const MARKER_LABELS = LABELS;
