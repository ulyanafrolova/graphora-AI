import { Link } from "react-router";

import type { AnswerPart, AskResult } from "@/api/types";
import { DEFAULT, toPath, type RouteState } from "@/state/route";

export function citeParts(cite: string): { path: string; line: number | null; commit: string } {
  const at = cite.lastIndexOf("@");
  const where = at < 0 ? cite : cite.slice(0, at);
  const m = /^(.*):(\d+)$/.exec(where);
  return { path: m?.[1] ?? where, line: m?.[2] ? Number(m[2]) : null, commit: at < 0 ? "" : cite.slice(at + 1) };
}

function Cite({ part, route }: { part: AnswerPart; route: RouteState }) {
  const c = citeParts(part.cite);
  if (c.line === null) return <span className="mono muted">{part.cite}</span>;
  const to = toPath({
    ...DEFAULT,
    repository: route.repository,
    snapshot: route.snapshot,
    screen: "code",
    path: c.path,
    line: c.line,
  });
  return (
    <Link className="mono" to={to}>
      {`${c.path}:${c.line}`}
    </Link>
  );
}

export function AnswerCard({ result, route, model }: { result: AskResult; route: RouteState; model: string | null }) {
  const a = result.answer;
  return (
    <section className="panel answer">
      <div className="answer-head">
        <span className="pill role-explorer">Explorer</span>
        <span className="pill role-analyst">Analyst</span>
        <span className="pill verified">Reviewer ✓ verified</span>
        <span className="muted">{`${a.counts.tool_calls} tool calls · ${a.counts.revisions} revisions · ${model ?? "model"}`}</span>
      </div>
      <p className="summary">{a.summary}</p>
      {a.facts.map((f) => (
        <div key={f.cite + f.text} className="fact" data-testid="fact">
          <span className="check">✓</span> <Cite part={f} route={route} /> <span>{f.text}</span>
          <span className="mono muted">{citeParts(f.cite).commit.slice(0, 16)}</span>
        </div>
      ))}
      {a.likely.map((f) => (
        <div key={f.cite + f.text} className="fact likely" data-testid="likely">
          <span className="pill heuristic">likely</span> <Cite part={f} route={route} /> <span>{f.text}</span>
        </div>
      ))}
      {a.hypotheses.map((h) => (
        <div key={h.cite + h.text} className="hypothesis" data-testid="hypothesis">
          {`⚠ Hypothesis — ${h.text}. Not statically proven.`}
        </div>
      ))}
    </section>
  );
}

export function citedFiles(result: AskResult): string[] {
  const parts = [...result.answer.facts, ...result.answer.likely];
  return [...new Set(parts.map((p) => citeParts(p.cite).path).filter((p) => p && !p.includes("(")))].sort();
}
