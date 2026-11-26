import { AskPage } from "./agents/AskPage";
import { TracePage } from "./agents/TracePage";
import { CodePage } from "./code/CodePage";
import { GraphPage } from "./graph/GraphPage";
import { CyclesPage } from "./insights/CyclesPage";
import { HotspotsPage } from "./insights/HotspotsPage";
import { McpPage } from "./integrations/McpPage";
import { NotAvailable } from "./integrations/NotAvailable";
import type { RouteState } from "./state/route";
import { useRoute } from "./state/useRoute";

export function Screen() {
  const route = useRoute();
  if (route === null) return <h1>not found</h1>;
  return <ScreenFor route={route} />;
}

function ScreenFor({ route }: { route: RouteState }) {
  switch (route.screen) {
    case "graph":
      return <GraphPage key={`${route.repository}@${route.snapshot}`} route={route} />;
    case "code":
      return <CodePage route={route} />;
    case "cycles":
      return <CyclesPage route={route} />;
    case "hotspots":
      return <HotspotsPage route={route} />;
    case "ask":
      return <AskPage key={`${route.repository}@${route.snapshot}`} route={route} />;
    case "trace":
      return <TracePage route={route} />;
    case "mcp":
      return <McpPage route={route} />;
    case "pr-impact":
      return <NotAvailable title="PR impact" />;
    case "security":
      return <NotAvailable title="Security" />;
  }
}
