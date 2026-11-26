// Server-sent events of POST /api/v1/ask (specs/013-ask-sse contracts/http-api.md, research R9).
import { ApiError, request, url } from "./client";
import type { AskResult, TraceEvent } from "./types";

export interface ServerEvent {
  event: string;
  id: string | null;
  data: string;
}

export class EventParser {
  private decoder = new TextDecoder();
  private buffer = "";
  private event = "message";
  private id: string | null = null;
  private data: string[] = [];

  push(chunk: Uint8Array): ServerEvent[] {
    this.buffer += this.decoder.decode(chunk, { stream: true });
    const out: ServerEvent[] = [];
    let end: number;
    while ((end = this.buffer.search(/\r\n|\r|\n/)) >= 0) {
      if (this.buffer[end] === "\r" && end === this.buffer.length - 1) break; // a "\r\n" split across chunks
      const line = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + (this.buffer.startsWith("\r\n", end) ? 2 : 1));
      if (line === "") {
        if (this.data.length) out.push({ event: this.event, id: this.id, data: this.data.join("\n") });
        this.event = "message";
        this.id = null;
        this.data = [];
        continue;
      }
      if (line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
      if (field === "event") this.event = value;
      else if (field === "id") this.id = value;
      else if (field === "data") this.data.push(value);
    }
    return out;
  }
}

export interface AskBody {
  repository: string;
  snapshot: string;
  question: string;
}

export async function streamAsk(
  body: AskBody,
  opts: { onStep?: (step: TraceEvent) => void; signal?: AbortSignal },
): Promise<AskResult> {
  const response = await request(url("ask"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...(opts.signal ? { signal: opts.signal } : {}),
  });
  const reader = response.body?.getReader();
  if (!reader) throw new ApiError(0, "stream", "no response body");
  const parser = new EventParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const e of parser.push(value)) {
      const data: unknown = JSON.parse(e.data);
      if (e.event === "step") opts.onStep?.(data as TraceEvent);
      else if (e.event === "answer") return data as AskResult;
      else if (e.event === "error")
        throw new ApiError(0, "stream", String((data as { message?: unknown }).message ?? "error"));
    }
  }
  throw new ApiError(0, "stream", "the answer stream ended early");
}
