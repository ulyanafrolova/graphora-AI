import { useMemo } from "react";

import { CodeView, lineMarkers, MARKER_LABELS } from "./CodeView";
import { FileTree } from "./FileTree";
import { ProvenancePanel } from "./ProvenancePanel";
import "./code.css";

import { useDependencies, useDependents, useFileLines, useGraph } from "@/api/queries";
import type { Answer } from "@/api/types";
import { ItemLinks } from "@/graph/ItemLinks";
import { nodeName } from "@/graph/names";
import { ErrorState } from "@/shell/ErrorState";
import { Loading } from "@/shell/Loading";
import { snapshotOf, type RouteState } from "@/state/route";
import { useGo } from "@/state/useRoute";

function Links({
  title,
  answer,
  onOpen,
}: {
  title: string;
  answer: Answer | undefined;
  onOpen: (path: string) => void;
}) {
  return (
    <section className="panel">
      <div className="label">
        {title} · {answer?.total ?? 0}
      </div>
      <ItemLinks items={answer && (answer.items ?? [])} onOpen={(node) => onOpen(nodeName(node))} />
    </section>
  );
}

export function CodePage({ route }: { route: RouteState }) {
  const go = useGo();
  const snapshot = snapshotOf(route);
  const graph = useGraph(snapshot);
  const lines = useFileLines(snapshot, route.path);
  const target = route.path === null ? null : `file:${route.path}`;
  const dependencies = useDependencies(snapshot, target);
  const dependents = useDependents(snapshot, target);
  const markers = useMemo(
    () => (route.path && graph.data ? lineMarkers(route.path, graph.data.edges) : new Map()),
    [route.path, graph.data],
  );

  if (graph.error) return <ErrorState error={graph.error} onRetry={() => void graph.refetch()} />;
  if (!graph.data) return <Loading what="files" />;
  const open = (path: string) => go({ ...route, screen: "code", path, line: null });
  const chosen = route.line === null ? undefined : markers.get(route.line)?.edges[0];
  const status = graph.data.coverage.files.find((f) => f.path === route.path);

  return (
    <div className="code-page">
      <FileTree files={graph.data.coverage.files} selected={route.path} onOpen={open} />
      <section className="code-main">
        {route.path === null ? (
          <p className="muted">Choose a file.</p>
        ) : (
          <>
            <header className="code-header">
              <span className="mono">{route.path}</span>
              <span className="pill">@ {route.snapshot.slice(0, 7)}</span>
              {status && (
                <span className={`pill ${status.status === "analyzed" ? "analyzed" : ""}`}>
                  {status.language ?? "text"} · {status.status.replace("_", " ")}
                </span>
              )}
            </header>
            {lines.error ? (
              <ErrorState error={lines.error} />
            ) : (
              <div className="panel code-box">
                <CodeView
                  lines={lines.data}
                  markers={markers}
                  selected={route.line}
                  onSelect={(line) => go({ ...route, line })}
                />
              </div>
            )}
            <ul className="legend">
              {Object.entries(MARKER_LABELS).map(([k, label]) => (
                <li key={k}>
                  <i className={`marker ${k}`} aria-hidden="true" /> {label}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <aside className="code-side">
        {chosen && <ProvenancePanel edge={chosen} />}
        {target && <Links title="Outgoing" answer={dependencies.data} onOpen={open} />}
        {target && <Links title="Incoming" answer={dependents.data} onOpen={open} />}
      </aside>
    </div>
  );
}
