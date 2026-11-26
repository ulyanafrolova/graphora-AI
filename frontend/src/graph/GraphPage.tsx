import { useMemo } from "react";

import { GraphView } from "./GraphView";
import { Search } from "./Search";
import { SidePanel } from "./SidePanel";
import "./graph.css";

import { useComponents, useCycles, useGraph, useHotspots, useImpact } from "@/api/queries";
import { ErrorState } from "@/shell/ErrorState";
import { Loading } from "@/shell/Loading";
import type { RouteState } from "@/state/route";
import { useGo } from "@/state/useRoute";

export function GraphPage({ route }: { route: RouteState }) {
  const go = useGo();
  const snapshot = { repository: route.repository, snapshot: route.snapshot };
  const graph = useGraph(snapshot);
  const components = useComponents(snapshot);
  const cycles = useCycles(snapshot);
  const hotspots = useHotspots(snapshot);
  const hot = useMemo(() => new Set((hotspots.data?.items ?? []).slice(0, 10).map((i) => i.node)), [hotspots.data]);
  // fetched on selection, so that switching impact mode on does not wait for the service
  const impact = useImpact(snapshot, route.impact || route.node?.startsWith("file:") ? route.node : null);
  const impacted = useMemo(
    () => (route.impact && impact.data ? new Set((impact.data.items ?? []).map((i) => i.node)) : null),
    [route.impact, impact.data],
  );

  const failed = graph.error ?? components.error;
  const retry = () => {
    void graph.refetch();
    void components.refetch();
  };
  if (failed) return <ErrorState error={failed} onRetry={retry} />;
  if (!graph.data || !components.data) return <Loading what="graph" />;

  return (
    <div className="graph-page">
      <GraphView
        route={route}
        graph={graph.data}
        components={components.data}
        impact={impacted}
        cycles={cycles.data}
        hot={hot}
        onChange={(next) => go({ ...route, ...next })}
        search={
          <Search
            snapshot={snapshot}
            graph={graph.data}
            onPick={(node) => go({ ...route, node, level: route.level === "system" ? "file" : route.level })}
          />
        }
      />
      <SidePanel
        route={route}
        components={components.data}
        impact={route.impact ? impact.data : undefined}
        onChange={(next) => go({ ...route, ...next })}
      />
    </div>
  );
}
