import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";

import { AnswerCard, citedFiles } from "./AnswerCard";
import { clearRuns, listRuns, openHistory, saveRun, type History, type Run } from "./history";
import "./agents.css";

import { ApiError } from "@/api/client";
import { useInfo } from "@/api/queries";
import { streamAsk } from "@/api/sse";
import type { AskResult, TraceEvent } from "@/api/types";
import { ErrorState } from "@/shell/ErrorState";
import { DEFAULT, toPath, type RouteState } from "@/state/route";

const SUGGESTED = [
  "Which files depend on the most-used file?",
  "Where are the import cycles?",
  "Explain the largest component",
];

export function StepList({ steps }: { steps: TraceEvent[] }) {
  return (
    <ol className="steps">
      {steps.map((s) => (
        <li key={s.n} className={`role-${s.role}`}>
          <strong>{s.role}</strong>{" "}
          <span className="mono">{s.tool ? `${s.tool}(${JSON.stringify(s.args ?? {})})` : s.kind}</span>
          {s.detail && <span className="muted"> {s.detail}</span>}
        </li>
      ))}
    </ol>
  );
}

export function AskPage({ route }: { route: RouteState }) {
  const info = useInfo();
  const location = useLocation();
  const [question, setQuestion] = useState((location.state as { question?: string } | null)?.question ?? "");
  const [steps, setSteps] = useState<TraceEvent[]>([]);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<History | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    let live = true;
    void openHistory().then(async (h) => {
      const listed = await listRuns(h, route.repository, route.snapshot);
      if (live) {
        setHistory(h);
        setRuns(listed);
      }
    });
    return () => {
      live = false;
      abort.current?.abort();
    };
  }, [route.repository, route.snapshot]);

  async function ask(text: string) {
    if (!text.trim() || running) return;
    abort.current?.abort();
    abort.current = new AbortController();
    setRunning(true);
    setError(null);
    setResult(null);
    setSteps([]);
    try {
      const answer = await streamAsk(
        { repository: route.repository, snapshot: route.snapshot, question: text },
        { onStep: (s) => setSteps((all) => [...all, s]), signal: abort.current.signal },
      );
      setResult(answer);
      if (history) {
        await saveRun(history, {
          repository: route.repository,
          snapshot: route.snapshot,
          question: text,
          created: Date.now(),
          result: answer,
        });
        setRuns(await listRuns(history, route.repository, route.snapshot));
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError"))
        setError(e instanceof ApiError ? e : new ApiError(0, "network", String(e)));
    } finally {
      setRunning(false);
    }
  }

  const shown = result;
  const cited = shown ? citedFiles(shown) : [];
  const model = info.data?.ask.model ?? null;
  return (
    <div className="ask-page">
      <div className="ask-main">
        {info.data && !info.data.ask.enabled && (
          <p className="issue">Agents are off in this service: start graphora serve with a model (--model).</p>
        )}
        {error && <ErrorState error={error} onRetry={() => void ask(question)} />}
        {running && <StepList steps={steps} />}
        {shown && <AnswerCard result={shown} route={route} model={model} />}
        <div className="suggested">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setQuestion(q);
                void ask(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>
        <form
          className="ask-box"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
        >
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about architecture, dependencies, impact…"
            rows={2}
          />
          <button type="submit" className="primary" disabled={running}>
            Ask
          </button>
        </form>
      </div>
      <aside className="ask-side">
        <section className="panel">
          <div className="label">Highlighted on graph</div>
          <ul className="rows">
            {cited.map((p) => (
              <li key={p}>
                <Link
                  className="mono"
                  to={toPath({ ...DEFAULT, repository: route.repository, snapshot: route.snapshot, node: `file:${p}` })}
                >
                  {p}
                </Link>
              </li>
            ))}
            {cited.length === 0 && <li className="muted">no cited files yet</li>}
          </ul>
        </section>
        <section className="panel">
          <div className="label">Earlier answers</div>
          {history && !history.persistent && <p className="muted">This browser will not keep the history.</p>}
          <ul className="rows">
            {runs.map((r) => (
              <li key={r.created}>
                <button type="button" className="link" onClick={() => setResult(r.result)}>
                  {r.question}
                </button>
                <Link to={toPath({ ...route, screen: "trace", run: String(r.created) })}>trace</Link>
              </li>
            ))}
          </ul>
          {runs.length > 0 && (
            <button
              type="button"
              onClick={() =>
                history && void clearRuns(history, route.repository, route.snapshot).then(() => setRuns([]))
              }
            >
              Clear history
            </button>
          )}
        </section>
      </aside>
    </div>
  );
}
