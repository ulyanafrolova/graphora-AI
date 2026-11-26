import { GraphPage } from "./graph/GraphPage";
import type { RouteState } from "./state/route";
import { useRoute } from "./state/useRoute";

function Soon({ name }: { name: string }) {
  return <h1>{name}</h1>;
}

export function Screen() {
  const route = useRoute();
  if (route === null) return <h1>not found</h1>;
  return <ScreenFor route={route} />;
}

function ScreenFor({ route }: { route: RouteState }) {
  switch (route.screen) {
    case "graph":
      return <GraphPage key={`${route.repository}@${route.snapshot}`} route={route} />;
    default:
      return <Soon name={route.screen} />;
  }
}
