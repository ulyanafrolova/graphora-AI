import { useQueries } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { CutCard } from "./CutCard";
import { CycleList } from "./CycleList";
import "./insights.css";

import { apiGet } from "@/api/client";
import { useCycles } from "@/api/queries";
import type { FileLines } from "@/api/types";
import { nodeName } from "@/graph/names";
import { ErrorState } from "@/shell/ErrorState";
import { Loading } from "@/shell/Loading";
import { toPath, type RouteState } from "@/state/route";
import { useGo } from "@/state/useRoute";

export function CyclesPage({ route }: { route: RouteState }) {
  const go = useGo();
  const navigate = useNavigate();
  const snapshot = { repository: route.repository, snapshot: route.snapshot };
  const cycles = useCycles(snapshot);
  const groups = cycles.data?.groups ?? [];
  const index = route.group !== null && route.group <= groups.length ? route.group - 1 : groups.length ? 0 : null;
  const group = index === null ? null : groups[index];
  const wanted = (group?.suggested_cut?.links ?? []).flatMap((l) =>
    l.edges[0] ? [{ path: nodeName(l.edges[0].source), line: l.edges[0].line }] : [],
  );
  const texts = useQueries({
    queries: wanted.map((w) => ({
      queryKey: ["file", { ...snapshot, path: w.path, start: w.line, end: w.line }],
      queryFn: () => apiGet<FileLines>("file", { ...snapshot, path: w.path, start: w.line, end: w.line }),
    })),
  });
  const lines = new Map(wanted.map((w, i) => [`${w.path}:${w.line}`, texts[i]?.data?.lines[0]?.text ?? ""]));

  if (cycles.error) return <ErrorState error={cycles.error} onRetry={() => void cycles.refetch()} />;
  if (!cycles.data) return <Loading what="cycles" />;
  const modules = new Set(groups.flatMap((g) => g.files)).size;
  return (
    <div className="insight-page">
      <header className="insight-head">
        <div>
          <h1>Cycles</h1>
          <p className="muted">
            Circular dependencies found with graph algorithms · suggestions are recommendations only
          </p>
        </div>
        <span className={cycles.data.total > 0 ? "pill cycle" : "pill resolved"}>
          {cycles.data.total} cycles · {modules} modules
        </span>
      </header>
      <div className="cycles-grid">
        <CycleList groups={groups} selected={index} onSelect={(i) => go({ ...route, group: i + 1 })} />
        {group && (
          <section className="panel">
            <div className="label">Before</div>
            <ul className="rows">
              {group.cycle.map((l) => {
                const cut = group.suggested_cut?.links.some((c) => c.source === l.source && c.target === l.target);
                return (
                  <li key={`${l.source}->${l.target}`} className={cut ? "cut" : ""}>
                    <span className="mono">{`${nodeName(l.source)} → ${nodeName(l.target)}`}</span>
                    <span className="mono muted">
                      {l.edges[0] ? `${nodeName(l.edges[0].source)}:${l.edges[0].line}` : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
            <div className="label">After (suggested)</div>
            <ul className="rows">
              {group.cycle
                .filter((l) => !group.suggested_cut?.links.some((c) => c.source === l.source && c.target === l.target))
                .map((l) => (
                  <li key={`${l.source}->${l.target}`}>
                    <span className="mono">{`${nodeName(l.source)} → ${nodeName(l.target)}`}</span>
                  </li>
                ))}
            </ul>
          </section>
        )}
        {group && (
          <CutCard
            group={group}
            lines={lines}
            onAsk={(question) => void navigate(toPath({ ...route, screen: "ask" }), { state: { question } })}
          />
        )}
      </div>
    </div>
  );
}
