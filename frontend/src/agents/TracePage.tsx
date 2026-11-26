import { useEffect, useState } from "react";
import { Link } from "react-router";

import { TraceView } from "./TraceView";
import { listRuns, openHistory, type Run } from "./history";
import "./agents.css";

import { useInfo } from "@/api/queries";
import { toPath, type RouteState } from "@/state/route";

export function TracePage({ route }: { route: RouteState }) {
  const info = useInfo();
  const [runs, setRuns] = useState<Run[] | null>(null);
  useEffect(() => {
    let live = true;
    void openHistory()
      .then((h) => listRuns(h, route.repository, route.snapshot))
      .then((r) => live && setRuns(r));
    return () => {
      live = false;
    };
  }, [route.repository, route.snapshot]);
  if (runs === null) return null;
  const run = runs.find((r) => String(r.created) === route.run) ?? runs[0];
  if (!run)
    return (
      <p className="muted">
        No answers yet. <Link to={toPath({ ...route, screen: "ask" })}>Ask agents</Link>
      </p>
    );
  return <TraceView question={run.question} result={run.result} limits={info.data?.ask.limits ?? null} />;
}
