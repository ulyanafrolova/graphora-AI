import type { AskResult, TraceEvent } from "@/api/types";

export interface ClaimRow {
  cite: string;
  status: string;
  reason: string | null;
}

/** One row per claim key: its last verdict, or "hypothesis" when the reviewer kept it as one. */
export function claimRows(trace: TraceEvent[]): ClaimRow[] {
  const rows = new Map<string, ClaimRow>();
  for (const e of trace) {
    if (e.kind === "verdict" && e.key)
      rows.set(e.key, { cite: e.cite ?? "", status: e.status ?? "", reason: e.reason ?? null });
    if (e.kind === "hypothesis" && e.key)
      rows.set(e.key, { cite: e.cite ?? "", status: "hypothesis", reason: e.reason ?? null });
  }
  return [...rows.values()];
}

const PILL: Record<string, string> = {
  verified: "verified",
  rejected: "rejected",
  hypothesis: "hypothesis",
  heuristic: "heuristic",
};

function describe(e: TraceEvent): string {
  if (e.tool) return `${e.tool}(${JSON.stringify(e.args ?? {})})`;
  if (e.kind === "claim" || e.kind === "verdict" || e.kind === "hypothesis") return `${e.kind} ${e.cite ?? ""}`;
  return e.kind;
}

export function TraceView({
  question,
  result,
  limits,
}: {
  question: string;
  result: AskResult;
  limits: { tool_calls: number; revisions: number } | null;
}) {
  const tools = result.trace.filter((e) => e.kind === "tool_call").length;
  const revisions = result.trace.filter((e) => e.kind === "revision").length;
  return (
    <div className="trace-page">
      <header>
        <h1>Agent trace</h1>
        <p className="muted">“{question}” · every tool call is logged</p>
      </header>
      <div className="trace-grid">
        <ol className="panel timeline">
          {result.trace.map((e) => (
            <li key={e.n} data-testid="trace-row" className={`role-${e.role}`}>
              <strong>{e.role}</strong> <span className="mono">{describe(e)}</span>
              {e.detail && <div className={e.kind === "revision" ? "revision" : "muted"}>{e.detail}</div>}
              {e.status && <span className={`pill ${PILL[e.status] ?? ""}`}>{e.status}</span>}
            </li>
          ))}
        </ol>
        <aside className="trace-side">
          <section className="panel">
            <div className="label">Agent flow</div>
            <p className="flow">
              <span className="pill role-explorer">Explorer</span> → <span className="pill role-analyst">Analyst</span>{" "}
              → <span className="pill heuristic">Reviewer</span>
            </p>
            {revisions > 0 && <p className="revision">request_revision · needs evidence</p>}
          </section>
          <section className="panel">
            <div className="label">Claims</div>
            <table className="risks">
              <tbody>
                {claimRows(result.trace).map((c) => (
                  <tr key={c.cite + c.status}>
                    <td className="mono">{c.cite.split("@")[0]}</td>
                    <td>
                      <span className={`pill ${PILL[c.status] ?? ""}`}>{c.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <div className="label">Budget</div>
            <p>
              Tool calls <span className="mono">{limits ? `${tools} / ${limits.tool_calls}` : tools}</span>
            </p>
            <p>
              Revisions <span className="mono">{limits ? `${revisions} / ${limits.revisions}` : revisions}</span>
            </p>
            <p className="muted">Tools are read-only. Repository text is treated as data, never as instructions.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
