import { readFileSync } from "node:fs";

import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { server } from "../setup";

import { EventParser, streamAsk } from "@/api/sse";

const enc = new TextEncoder();

test("events across chunks, multi-line data, CRLF, comments and split UTF-8", () => {
  const p = new EventParser();
  const bytes = enc.encode(": hi\r\nevent: step\r\nid: 1\r\ndata: {\"a\":\r\ndata: \"é\"}\r\n\r\nevent: answer\ndata: {}\n\n");
  const out = [];
  for (let i = 0; i < bytes.length; i += 3) out.push(...p.push(bytes.slice(i, i + 3)));
  expect(out).toEqual([
    { event: "step", id: "1", data: '{"a":\n"é"}' },
    { event: "answer", id: null, data: "{}" },
  ]);
});

test("streamAsk yields steps and resolves with the answer", async () => {
  const body = readFileSync(new URL("../fixtures/ask.sse", import.meta.url));
  let sent: unknown = null;
  server.use(
    http.post("*/api/v1/ask", async ({ request }) => {
      sent = await request.json();
      return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
    }),
  );
  const steps: number[] = [];
  const result = await streamAsk({ repository: "r", snapshot: "s", question: "q" }, { onStep: (s) => steps.push(s.n) });
  expect(sent).toEqual({ repository: "r", snapshot: "s", question: "q" });
  expect(steps).toEqual(Array.from({ length: 18 }, (_, i) => i + 1));
  expect(result.answer.facts).toHaveLength(2);
  expect(result.trace).toHaveLength(18);
});

test("busy and error events reject", async () => {
  server.use(http.post("*/api/v1/ask", () => HttpResponse.json({ error: { kind: "busy", message: "busy" } }, { status: 429 })));
  await expect(streamAsk({ repository: "r", snapshot: "s", question: "q" }, {})).rejects.toMatchObject({ kind: "busy" });
  server.use(
    http.post("*/api/v1/ask", () =>
      new HttpResponse('event: error\ndata: {"message": "internal error"}\n\n', { headers: { "Content-Type": "text/event-stream" } }),
    ),
  );
  await expect(streamAsk({ repository: "r", snapshot: "s", question: "q" }, {})).rejects.toMatchObject({ kind: "stream", message: "internal error" });
});
