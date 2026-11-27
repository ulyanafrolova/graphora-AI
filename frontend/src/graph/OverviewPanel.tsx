import { useComponents, useCycles, useOverview, type Snapshot } from "@/api/queries";
import { shortSnapshot } from "@/shell/Header";
import { thousands } from "@/shell/format";


export function OverviewPanel({ snapshot }: { snapshot: Snapshot }) {
  const overview = useOverview(snapshot);
  const components = useComponents(snapshot);
  const cycles = useCycles(snapshot);
  return (
    <aside className="side-panel" data-testid="overview-panel">
      <div className="label">Repository</div>
      <h2 className="mono">
        {snapshot.repository} @ {shortSnapshot(snapshot.snapshot)}
      </h2>
      <div className="stats two">
        <div className="stat" data-testid="stat-files">
          <span className="muted">Files</span>
          <strong>{thousands(overview.data?.files.analyzed)}</strong>
        </div>
        <div className="stat" data-testid="stat-edges">
          <span className="muted">Edges</span>
          <strong>{thousands(overview.data?.edges)}</strong>
        </div>
        <div className="stat" data-testid="stat-components">
          <span className="muted">Components</span>
          <strong>{thousands(components.data?.total)}</strong>
        </div>
        <div className="stat" data-testid="stat-cycles">
          <span className="muted">Cycles</span>
          <strong className={cycles.data?.total ? "cycle-text" : ""}>{thousands(cycles.data?.total)}</strong>
        </div>
      </div>
      <div className="label">How it stays readable</div>
      <ul className="plain">
        <li>Louvain clusters → components</li>
        <li>Links between components are bundled</li>
        <li>Labels appear as you zoom in</li>
        <li>Collapse / expand any component</li>
      </ul>
      <div className="label">Legend</div>
      <ul className="plain">
        <li>node size = number of dependents</li>
        <li>
          <span className="hot-dot" /> hotspot (churn × centrality)
        </li>
        <li>
          <span className="cycle-text">—</span> link with a cycle
        </li>
      </ul>
    </aside>
  );
}
