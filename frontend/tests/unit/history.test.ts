import { beforeEach, expect, test } from "vitest";

import type { AskResult } from "@/api/types";
import { clearRuns, listRuns, openHistory, saveRun } from "@/agents/history";

const result = { answer: { facts: [] }, trace: [] } as unknown as AskResult;

beforeEach(async () => {
  const h = await openHistory();
  await clearRuns(h, "r", "s");
  await clearRuns(h, "r", "t");
});

test("keeps the newest 20 per snapshot, newest first", async () => {
  const h = await openHistory();
  expect(h.persistent).toBe(true);
  for (let i = 1; i <= 23; i++) await saveRun(h, { repository: "r", snapshot: "s", question: `q${i}`, created: i, result });
  await saveRun(h, { repository: "r", snapshot: "t", question: "other", created: 1, result });
  const runs = await listRuns(h, "r", "s");
  expect(runs.map((r) => r.question)).toEqual(Array.from({ length: 20 }, (_, i) => `q${23 - i}`));
  expect((await listRuns(h, "r", "t")).map((r) => r.question)).toEqual(["other"]);
});

test("clear one snapshot", async () => {
  const h = await openHistory();
  await saveRun(h, { repository: "r", snapshot: "s", question: "q", created: 1, result });
  await saveRun(h, { repository: "r", snapshot: "t", question: "q", created: 1, result });
  await clearRuns(h, "r", "s");
  expect(await listRuns(h, "r", "s")).toEqual([]);
  expect(await listRuns(h, "r", "t")).toHaveLength(1);
});

test("without indexedDB answers are kept in memory only", async () => {
  const h = await openHistory(null);
  expect(h.persistent).toBe(false);
  await saveRun(h, { repository: "r", snapshot: "s", question: "q", created: 1, result });
  expect(await listRuns(h, "r", "s")).toHaveLength(1);
});
