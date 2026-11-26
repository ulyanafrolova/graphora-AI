// The last 20 answers per snapshot, in the browser only (specs/019-frontend clarification Q4, research R10).
import { openDB, type IDBPDatabase } from "idb";

import type { AskResult } from "@/api/types";

export interface Run {
  repository: string;
  snapshot: string;
  question: string;
  created: number;
  result: AskResult;
}

export interface History {
  persistent: boolean;
  db: IDBPDatabase | null;
  memory: Run[];
}

const KEEP = 20;

export async function openHistory(factory: IDBFactory | null = globalThis.indexedDB ?? null): Promise<History> {
  if (factory === null) return { persistent: false, db: null, memory: [] };
  try {
    const db = await openDB("graphora", 1, {
      upgrade(d) {
        d.createObjectStore("answers", { keyPath: ["repository", "snapshot", "created"] });
      },
    });
    return { persistent: true, db, memory: [] };
  } catch {
    return { persistent: false, db: null, memory: [] };
  }
}

const range = (repository: string, snapshot: string) =>
  IDBKeyRange.bound([repository, snapshot, -Infinity], [repository, snapshot, Infinity]);

export async function listRuns(h: History, repository: string, snapshot: string): Promise<Run[]> {
  const runs = h.db
    ? ((await h.db.getAll("answers", range(repository, snapshot))) as Run[])
    : h.memory.filter((r) => r.repository === repository && r.snapshot === snapshot);
  return [...runs].sort((a, b) => b.created - a.created);
}

export async function saveRun(h: History, run: Run): Promise<void> {
  if (h.db) await h.db.put("answers", run);
  else h.memory.push(run);
  const old = (await listRuns(h, run.repository, run.snapshot)).slice(KEEP);
  for (const r of old) {
    if (h.db) await h.db.delete("answers", [r.repository, r.snapshot, r.created]);
    else h.memory.splice(h.memory.indexOf(r), 1);
  }
}

export async function clearRuns(h: History, repository: string, snapshot: string): Promise<void> {
  if (h.db) await h.db.delete("answers", range(repository, snapshot));
  else h.memory = h.memory.filter((r) => !(r.repository === repository && r.snapshot === snapshot));
}
