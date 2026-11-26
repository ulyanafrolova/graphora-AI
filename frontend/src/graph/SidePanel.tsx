import { useNavigate } from "react-router";

import { ComponentPanel } from "./ComponentPanel";
import { FilePanel } from "./FilePanel";
import { ImpactPanel } from "./ImpactPanel";
import { OverviewPanel } from "./OverviewPanel";
import { nodeName } from "./names";

import { useCycles, useFiles, useHotspots, useKeyFiles, useNeighbors } from "@/api/queries";
import type { Answer } from "@/api/types";
import { toPath, type RouteState } from "@/state/route";

export interface SidePanelProps {
  route: RouteState;
  components: Answer;
  impact: Answer | undefined;
  onChange: (next: Partial<RouteState>) => void;
}

export function SidePanel({ route, components, impact, onChange }: SidePanelProps) {
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
      >
        {route.impact && impact !== undefined && <ImpactPanel answer={impact} components={components} />}
      </FilePanel>
    );
  }
  if (route.node === null && route.level !== "component") return <OverviewPanel snapshot={snapshot} />;
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
