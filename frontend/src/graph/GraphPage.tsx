import { useMemo } from "react";

import { GraphView } from "./GraphView";
import { SidePanel } from "./SidePanel";
import "./graph.css";

import { useComponents, useCycles, useGraph, useImpact } from "@/api/queries";
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
  const impact = useImpact(snapshot, route.impact ? route.node : null);
  const impacted = useMemo(
    () => (route.impact && impact.data ? new Set((impact.data.items ?? []).map((i) => i.node)) : null),
    [route.impact, impact.data],
  );

  const failed = graph.error ?? components.error;
  if (failed) return <ErrorState error={failed} onRetry={() => void graph.refetch()} />;
  if (!graph.data || !components.data) return <Loading what="graph" />;

  return (
    <div className="graph-page">
      <GraphView
        route={route}
        graph={graph.data}
        components={components.data}
        impact={impacted}
        cycles={cycles.data}
        onChange={(next) => go({ ...route, ...next })}
      />
      <SidePanel
        route={route}
        components={components.data}
        impact={impact.data}
        onChange={(next) => go({ ...route, ...next })}
      />
    </div>
  );
}
