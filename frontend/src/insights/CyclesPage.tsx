import { CutCard } from "./CutCard";
import { CycleList } from "./CycleList";
import "./insights.css";

import { useCycles, useLineTexts } from "@/api/queries";
import { nodeName } from "@/graph/names";
import { ErrorState } from "@/shell/ErrorState";
import { Loading } from "@/shell/Loading";
import { snapshotOf, type RouteState } from "@/state/route";
import { useAsk, useGo } from "@/state/useRoute";

export function CyclesPage({ route }: { route: RouteState }) {
  const go = useGo();
  const askAbout = useAsk();
  const snapshot = snapshotOf(route);
  const cycles = useCycles(snapshot);
  const groups = cycles.data?.groups ?? [];
  const index = route.group !== null && route.group <= groups.length ? route.group - 1 : groups.length ? 0 : null;
  const group = index === null ? null : groups[index];
  const wanted = (group?.suggested_cut?.links ?? []).flatMap((l) =>
    l.edges[0] ? [{ path: nodeName(l.edges[0].source), line: l.edges[0].line }] : [],
  );
  const lines = useLineTexts(snapshot, wanted);

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
        {group && <CutCard group={group} lines={lines} onAsk={(question) => askAbout(route, question)} />}
      </div>
    </div>
  );
}
