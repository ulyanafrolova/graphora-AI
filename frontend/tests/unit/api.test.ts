import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { server } from "../setup";

import { ApiError, apiGet, apiPost, apiUpload } from "@/api/client";


test("get builds the address and parses json", async () => {
  let seen = "";
  server.use(
    http.get("*/api/v1/impact", ({ request }) => {
      seen = new URL(request.url).search;
      return HttpResponse.json({ total: 1 });
    }),
  );
  const body = await apiGet<{ total: number }>("impact", { repository: "a/b", snapshot: "content:1", target: "x y.py", limit: 5 });
  expect(body.total).toBe(1);
  expect(seen).toBe("?repository=a%2Fb&snapshot=content%3A1&target=x%20y.py&limit=5");
});

test("undefined parameters are left out", async () => {
  let seen = "";
  server.use(
    http.get("*/api/v1/cycles", ({ request }) => {
      seen = new URL(request.url).search;
      return HttpResponse.json({});
    }),
  );
  await apiGet("cycles", { repository: "r", snapshot: "s", level: undefined });
  expect(seen).toBe("?repository=r&snapshot=s");
});

test("error bodies become ApiError", async () => {
  server.use(
    http.get("*/api/v1/graph", () =>
      HttpResponse.json({ error: { kind: "stale", message: "analyze it again" } }, { status: 409 }),
    ),
  );
  const error = await apiGet("graph", { repository: "r", snapshot: "s" }).catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 409, kind: "stale", message: "analyze it again", retryAfter: null });
});

test("retry-after is read", async () => {
  server.use(
    http.post("*/api/v1/ask", () =>
      HttpResponse.json({ error: { kind: "busy", message: "busy" } }, { status: 429, headers: { "Retry-After": "30" } }),
    ),
  );
  const error = await apiPost("ask", { question: "q" }).catch((e: unknown) => e);
  expect(error).toMatchObject({ status: 429, kind: "busy", retryAfter: 30 });
});

test("a body that is not the error shape still gives a kind", async () => {
  server.use(http.get("*/api/v1/info", () => new HttpResponse("oops", { status: 502 })));
  const error = await apiGet("info").catch((e: unknown) => e);
  expect(error).toMatchObject({ status: 502, kind: "http_502" });
});

test("network failure is kind network", async () => {
  server.use(http.get("*/api/v1/info", () => HttpResponse.error()));
  const error = await apiGet("info").catch((e: unknown) => e);
  expect(error).toMatchObject({ status: 0, kind: "network" });
});

test("post sends json and upload sends bytes", async () => {
  let json: unknown = null;
  let bytes = 0;
  let name = "";
  server.use(
    http.post("*/api/v1/jobs", async ({ request }) => {
      json = await request.json();
      return HttpResponse.json({ id: "j1" }, { status: 202 });
    }),
    http.post("*/api/v1/jobs/zip", async ({ request }) => {
      name = new URL(request.url).searchParams.get("name") ?? "";
      bytes = (await request.arrayBuffer()).byteLength;
      return HttpResponse.json({ id: "j2" }, { status: 202 });
    }),
  );
  expect(await apiPost("jobs", { github: "https://github.com/o/r" })).toEqual({ id: "j1" });
  expect(json).toEqual({ github: "https://github.com/o/r" });
  expect(await apiUpload("jobs/zip", { name: "app.zip" }, new Blob([new Uint8Array(10)]))).toEqual({ id: "j2" });
  expect([name, bytes]).toEqual(["app.zip", 10]);
});
