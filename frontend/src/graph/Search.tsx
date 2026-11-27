import { useDeferredValue, useState } from "react";

import { nodeName } from "./names";

import { useDefinitions, type Snapshot } from "@/api/queries";
import type { GraphDocument } from "@/api/types";
import { PathLabel } from "@/shell/PathLabel";

export function matchFiles(graph: GraphDocument, text: string): string[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return [];
  return graph.nodes
    .filter((n) => n.kind === "file" && n.id.toLowerCase().includes(needle))
    .map((n) => n.id)
    .sort()
    .slice(0, 20);
}

const IDENTIFIER = /^[A-Za-z_][\w.]*$/;

export function Search({
  snapshot,
  graph,
  onPick,
}: {
  snapshot: Snapshot;
  graph: GraphDocument;
  onPick: (node: string) => void;
}) {
  const [text, setText] = useState("");
  const query = useDeferredValue(text.trim());
  const definitions = useDefinitions(snapshot, IDENTIFIER.test(query) ? query : null);
  const files = matchFiles(graph, query);
  const defs = definitions.data?.definitions ?? [];
  const choose = (node: string) => {
    setText("");
    onPick(node);
  };
  return (
    <div className="search">
      <input
        type="search"
        role="searchbox"
        placeholder={`Search ${graph.nodes.filter((n) => n.kind === "file").length} files, symbols…`}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {query && (
        <ul className="search-results panel">
          {files.map((f) => {
            const path = nodeName(f);
            return (
              <li key={f}>
                <button type="button" className="mono" title={path} aria-label={path} onClick={() => choose(f)}>
                  <PathLabel path={path} />
                </button>
              </li>
            );
          })}
          {defs.map((d) => {
            const where = `${d.path}:${d.line}`;
            const label = `${where} · ${d.kind} ${d.name}`;
            return (
              <li key={`${where}:${d.name}`}>
                <button type="button" className="mono" title={label} aria-label={label} onClick={() => choose(d.file)}>
                  <span className="path-name">{`${d.kind} ${d.name}`}</span>
                  <span className="path-dir">{where}</span>
                </button>
              </li>
            );
          })}
          {IDENTIFIER.test(query) && definitions.isSuccess && defs.length === 0 && (
            <li className="muted">no definitions</li>
          )}
        </ul>
      )}
    </div>
  );
}
