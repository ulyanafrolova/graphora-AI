import { Navigate, type RouteObject } from "react-router";

import { DEFAULT, lastSnapshot, toPath } from "./state/route";
import { useRoute } from "./state/useRoute";

function Home() {
  const last = lastSnapshot();
  return <Navigate replace to={last ? toPath({ ...DEFAULT, ...last }) : "/import"} />;
}

function Placeholder({ name }: { name?: string }) {
  const route = useRoute();
  return <main>{name ?? route?.screen ?? "not found"}</main>;
}

export const routes: RouteObject[] = [
  { path: "/", element: <Home /> },
  { path: "/import", element: <Placeholder name="import" /> },
  { path: "/r/:repo/:snap/:screen", element: <Placeholder /> },
  { path: "*", element: <Placeholder name="not found" /> },
];
