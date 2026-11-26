import { useEffect, useMemo, useSyncExternalStore } from "react";
import { Outlet, useLocation } from "react-router";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { SnapshotPicker } from "./SnapshotPicker";

import { useGraph, useInfo } from "@/api/queries";
import {
  DEFAULT,
  lastSnapshotText,
  onLastSnapshot,
  parseLastSnapshot,
  rememberSnapshot,
  type RouteState,
} from "@/state/route";
import { useRoute } from "@/state/useRoute";

import "./shell.css";

export function Layout() {
  const route = useRoute();
  const location = useLocation();
  // on Import the header and the menu keep the last opened snapshot, so its screens stay one click away
  const lastText = useSyncExternalStore(onLastSnapshot, lastSnapshotText);
  const context = useMemo((): RouteState | null => {
    if (route !== null) return route;
    const last = parseLastSnapshot(lastText);
    return last === null ? null : { ...DEFAULT, ...last, screen: "graph" };
  }, [route, lastText]);
  const snapshot = context === null ? null : { repository: context.repository, snapshot: context.snapshot };
  const graph = useGraph(snapshot);
  const info = useInfo();
  const note = (location.state as { note?: string | null } | null)?.note ?? null;

  useEffect(() => {
    if (route !== null && graph.isSuccess) rememberSnapshot(route.repository, route.snapshot);
  }, [route, graph.isSuccess]);

  return (
    <div className="app">
      <Header
        repository={context?.repository ?? null}
        snapshot={context?.snapshot ?? null}
        files={graph.data?.coverage.files ?? []}
        ask={info.data?.ask ?? null}
        picker={<SnapshotPicker route={context} />}
      />
      <div className="body">
        <Sidebar route={context} current={route?.screen ?? null} />
        <main className="content">
          {note !== null && <p className="note">{note}</p>}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
