import { TopRisks } from "./TopRisks";
import { historyLine, Treemap } from "./Treemap";
import "./insights.css";

import { useFiles, useHotspots } from "@/api/queries";
import { ErrorState } from "@/shell/ErrorState";
import { Loading } from "@/shell/Loading";
import type { RouteState } from "@/state/route";
import { useGo } from "@/state/useRoute";

export function HotspotsPage({ route }: { route: RouteState }) {
  const go = useGo();
  const snapshot = { repository: route.repository, snapshot: route.snapshot };
  const hotspots = useHotspots(snapshot);
  const files = useFiles(snapshot);
  if (hotspots.error) return <ErrorState error={hotspots.error} onRetry={() => void hotspots.refetch()} />;
  if (!hotspots.data) return <Loading what="hotspots" />;
  const lines = new Map((files.data?.files ?? []).map((f) => [f.path, f.line_count]));
  const history = hotspots.data.history;
  const open = (node: string) => go({ ...route, screen: "graph", node });
  const available = history !== undefined && history.status !== "not_available";
  return (
    <div className="insight-page">
      <header className="insight-head">
        <div>
          <h1>Hotspots</h1>
          <p className="muted">
            Risk = commits in the 12 months before the snapshot × files that depend on it (transitively)
          </p>
        </div>
        <span className="legend-ramp">
          low <i /> high
        </span>
      </header>
      {history && <p className={available ? "muted" : "issue"}>{historyLine(history)}</p>}
      {available && (
        <div className="hotspots-grid">
          <section className="panel">
            <div className="label">Risk map · size = lines of code</div>
            {(hotspots.data.items ?? []).length ? (
              <Treemap items={hotspots.data.items ?? []} lines={lines} onOpen={open} />
            ) : (
              <p className="muted">No hotspots.</p>
            )}
          </section>
          <section className="panel">
            <div className="label">Top risks</div>
            <TopRisks answer={hotspots.data} onOpen={open} />
          </section>
        </div>
      )}
    </div>
  );
}
