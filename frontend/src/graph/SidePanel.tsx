import { useNavigate } from "react-router";

import { ComponentPanel } from "./ComponentPanel";
import { FilePanel } from "./FilePanel";
import { nodeName } from "./names";

import { useCycles, useFiles, useHotspots, useKeyFiles, useNeighbors } from "@/api/queries";
import type { Answer } from "@/api/types";
import { toPath, type RouteState } from "@/state/route";

export function SidePanel({
  route,
  components,
  onChange,
}: {
  route: RouteState;
  components: Answer;
  onChange: (next: Partial<RouteState>) => void;
}) {
  const navigate = useNavigate();
  const snapshot = { repository: route.repository, snapshot: route.snapshot };
  const keyFiles = useKeyFiles(snapshot);
  const cycles = useCycles(snapshot);
  const files = useFiles(snapshot);
  const hotspots = useHotspots(snapshot);
  const file = route.node?.startsWith("file:") ? route.node : null;
  const neighbors = useNeighbors(snapshot, file);
  const ask = (question: string) => void navigate(toPath({ ...route, screen: "ask" }), { state: { question } });

  if (file !== null) {
    return (
      <FilePanel
        node={file}
        files={files.data}
        keyFiles={keyFiles.data}
        hotspots={hotspots.data}
        neighbors={neighbors.data}
        cycles={cycles.data}
        impact={route.impact}
        onToggleImpact={() => onChange({ impact: !route.impact })}
        onOpenCode={() => onChange({ screen: "code", path: nodeName(file), line: null })}
        onSelect={(id) => onChange({ node: id })}
      />
    );
  }
  const component = (components.components ?? []).find((c) => c.id === (route.node ?? route.component)) ?? null;
  return (
    <ComponentPanel
      component={component}
      components={components}
      keyFiles={keyFiles.data}
      cycles={cycles.data}
      files={files.data}
      onExpand={() => component && onChange({ level: "component", component: component.id, node: null })}
      onAsk={ask}
      onSelect={(id) => onChange({ node: id })}
    />
  );
}
