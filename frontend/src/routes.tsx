import { Navigate, type RouteObject } from "react-router";

import { Screen } from "./screens";
import { Layout } from "./shell/Layout";
import { DEFAULT, lastSnapshot, toPath } from "./state/route";
import { useRoute } from "./state/useRoute";

function Home() {
  const last = lastSnapshot();
  return <Navigate replace to={last ? toPath({ ...DEFAULT, ...last }) : "/import"} />;
}

function Placeholder({ name }: { name?: string }) {
  const route = useRoute();
  return <h1>{name ?? route?.screen ?? "not found"}</h1>;
}

export const routes: RouteObject[] = [
  { path: "/", element: <Home /> },
  {
    element: <Layout />,
    children: [
      { path: "/import", element: <Placeholder name="import" /> },
      { path: "/r/:repo/:snap/:screen", element: <Screen /> },
      { path: "*", element: <Placeholder name="not found" /> },
    ],
  },
];
