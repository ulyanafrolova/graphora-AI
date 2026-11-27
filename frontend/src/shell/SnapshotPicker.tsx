import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { shortSnapshot } from "./Header";

import { apiGet } from "@/api/client";
import { useRepositories } from "@/api/queries";
import type { GraphDocument } from "@/api/types";
import { DEFAULT, switchSnapshot, toPath, type RouteState } from "@/state/route";

export function SnapshotPicker({ route }: { route: RouteState | null }) {
  const [open, setOpen] = useState(false);
  const repositories = useRepositories();
  const client = useQueryClient();
  const navigate = useNavigate();
  const root = useRef<HTMLSpanElement>(null);

  // a click anywhere outside the picker, or Escape, closes the list
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  async function pick(repository: string, snapshot: string) {
    setOpen(false);
    const params = { repository, snapshot };
    const doc = await client
      .fetchQuery({ queryKey: ["graph", params], queryFn: () => apiGet<GraphDocument>("graph", params) })
      .catch(() => null);
    const ids = new Set(doc?.nodes.map((n) => n.id) ?? []);
    const next = switchSnapshot(route ?? DEFAULT, repository, snapshot, (id) => ids.has(id));
    void navigate(toPath(route === null ? { ...next.state, screen: "graph" } : next.state), {
      state: { note: next.note },
    });
  }

  return (
    <span className="picker" ref={root}>
      <button
        type="button"
        className="snapshot mono"
        title={route === null ? undefined : `${route.repository} @ ${route.snapshot}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {route === null ? (
          "choose a snapshot"
        ) : (
          <>
            <span className="repo">{route.repository}</span> <span className="at">@</span>{" "}
            <span>{shortSnapshot(route.snapshot)}</span>
          </>
        )}
      </button>
      {open && (
        <ul className="menu" role="listbox">
          {repositories.data?.repositories.flatMap((r) =>
            r.snapshots.map((s) => (
              <li
                key={`${r.name}@${s}`}
                role="option"
                aria-selected={route?.repository === r.name && route.snapshot === s}
              >
                <button type="button" onClick={() => void pick(r.name, s)}>
                  <span>{r.name}</span> @ <span className="mono">{shortSnapshot(s)}</span>
                </button>
              </li>
            )),
          )}
          {repositories.data?.repositories.length === 0 && <li className="muted">no stored snapshots</li>}
        </ul>
      )}
    </span>
  );
}
