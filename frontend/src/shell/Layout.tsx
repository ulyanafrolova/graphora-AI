import { useEffect } from "react";
import { Outlet, useLocation } from "react-router";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { SnapshotPicker } from "./SnapshotPicker";

import { useGraph, useInfo } from "@/api/queries";
import { rememberSnapshot } from "@/state/route";
import { useRoute } from "@/state/useRoute";

import "./shell.css";

export function Layout() {
  const route = useRoute();
  const location = useLocation();
  const snapshot = route === null ? null : { repository: route.repository, snapshot: route.snapshot };
  const graph = useGraph(snapshot);
  const info = useInfo();
  const note = (location.state as { note?: string | null } | null)?.note ?? null;

  useEffect(() => {
    if (route !== null && graph.isSuccess) rememberSnapshot(route.repository, route.snapshot);
  }, [route, graph.isSuccess]);

  return (
    <div className="app">
      <Header
        repository={route?.repository ?? null}
        snapshot={route?.snapshot ?? null}
        files={graph.data?.coverage.files ?? []}
        ask={info.data?.ask ?? null}
        picker={<SnapshotPicker route={route} />}
      />
      <div className="body">
        <Sidebar route={route} />
        <main className="content">
          {note !== null && <p className="note">{note}</p>}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
