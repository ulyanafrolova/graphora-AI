import { useEffect, useState } from "react";
import { Link } from "react-router";

import "./import.css";

import { ApiError, apiGet, apiPost, apiUpload } from "@/api/client";
import type { CoverageFile } from "@/api/graph.gen";
import { useGraph, useInfo } from "@/api/queries";
import type { Job, Limits, Stage } from "@/api/types";
import { ErrorState } from "@/shell/ErrorState";
import { languageName, shortSnapshot } from "@/shell/Header";
import { DEFAULT, toPath } from "@/state/route";

const STAGES: [Stage, string][] = [
  ["queued", "Queued"],
  ["resolving", "Snapshot commit"],
  ["fetching", "Fetch source"],
  ["analyzing", "Detect, parse and resolve"],
  ["storing", "Build graph and store"],
];

const thousands = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
const megabytes = (n: number) => `${Math.round(n / 1024 / 1024)} MB`;
const minutes = (s: number) => (s % 60 === 0 ? `${s / 60} min` : `${s} s`);

function LimitsPanel({ limits }: { limits: Limits | null }) {
  return (
    <section className="panel">
      <div className="label">Safety limits</div>
      {limits === null ? (
        <p className="muted">Analysis jobs are off in this service.</p>
      ) : (
        <dl className="limits">
          <dt>Max size</dt>
          <dd>{megabytes(limits.max_bytes)}</dd>
          <dt>Max files</dt>
          <dd>{thousands(limits.max_files)}</dd>
          <dt>Time budget</dt>
          <dd>{minutes(limits.max_seconds)}</dd>
          <dt>Skipped</dt>
          <dd className="mono">{limits.skipped.join(", ")}</dd>
        </dl>
      )}
      <p>
        Execution <span className="pill resolved">never — static analysis only</span>
      </p>
    </section>
  );
}

interface CoverageRow {
  name: string;
  files: number;
  depth: "full" | "detected only" | "not code";
}

export function coverageRows(files: CoverageFile[]): CoverageRow[] {
  const rows = new Map<string, CoverageRow>();
  for (const f of files) {
    const name = f.language === null || f.status === "not_code" ? "Other" : languageName(f.language);
    const depth = f.status === "analyzed" ? "full" : f.status === "detected_only" ? "detected only" : "not code";
    const row = rows.get(name) ?? { name, files: 0, depth };
    row.files += 1;
    if (depth === "full") row.depth = "full";
    rows.set(name, row);
  }
  const rank = { full: 0, "detected only": 1, "not code": 2 } as const;
  return [...rows.values()].sort(
    (a, b) => rank[a.depth] - rank[b.depth] || b.files - a.files || (a.name < b.name ? -1 : 1),
  );
}

function Coverage({ repository, snapshot }: { repository: string; snapshot: string }) {
  const graph = useGraph({ repository, snapshot });
  const rows = coverageRows(graph.data?.coverage.files ?? []);
  const total = rows.reduce((n, r) => n + r.files, 0) || 1;
  return (
    <section className="panel">
      <div className="label">Language coverage</div>
      <table className="coverage">
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} data-testid="coverage-row">
              <td>{r.name}</td>
              <td>{r.files}</td>
              <td aria-hidden="true">
                <i style={{ width: `${(100 * r.files) / total}%` }} />
              </td>
              <td>
                <span className={`pill ${r.depth === "full" ? "analyzed" : ""}`}>{r.depth}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function ImportPage({ poll = 1000 }: { poll?: number }) {
  const info = useInfo();
  const [tab, setTab] = useState<"github" | "zip">("github");
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [seen, setSeen] = useState<Stage[]>([]);

  useEffect(() => {
    if (job === null || job.stage === "done" || job.stage === "failed") return;
    const timer = setTimeout(() => {
      apiGet<Job>(`jobs/${encodeURIComponent(job.id)}`)
        .then((next) => {
          setSeen((s) => (s.includes(next.stage) ? s : [...s, next.stage]));
          setJob(next);
        })
        .catch((e: unknown) => setError(e instanceof ApiError ? e : new ApiError(0, "network", String(e))));
    }, poll);
    return () => clearTimeout(timer);
  }, [job, poll]);

  const start = (run: Promise<Job>) => {
    setError(null);
    setSeen([]);
    run
      .then((j) => {
        setSeen([j.stage]);
        setJob(j);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e : new ApiError(0, "network", String(e))));
  };
  const reset = () => {
    setJob(null);
    setSeen([]);
    setError(null);
  };
  // the service only moves a job forward, so every stage before the latest one seen has passed (a poll can miss one)
  const reached = Math.max(-1, ...seen.map((s) => STAGES.findIndex(([stage]) => stage === s)));
  const done = job?.stage === "done" && job.result ? job.result : null;
  const progressing = job !== null && !(job.stage === "done" && seen.length <= 1);

  return (
    <div className="import-page">
      <header>
        <h1>Import repository</h1>
        <p className="muted">Public GitHub repository or ZIP archive. Analysis is pinned to a single commit.</p>
      </header>
      <div className="import-grid">
        <div className="import-left">
          <section className="panel">
            <div className="tabs" role="tablist">
              <button type="button" role="tab" aria-selected={tab === "github"} onClick={() => setTab("github")}>
                GitHub URL
              </button>
              <button type="button" role="tab" aria-selected={tab === "zip"} onClick={() => setTab("zip")}>
                ZIP upload
              </button>
            </div>
            {tab === "github" ? (
              <form
                className="source"
                onSubmit={(e) => {
                  e.preventDefault();
                  start(apiPost<Job>("jobs", ref ? { github: url, ref } : { github: url }));
                }}
              >
                <label>
                  GitHub URL
                  <input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://github.com/owner/repo"
                    required
                  />
                </label>
                <label>
                  Branch, tag or commit
                  <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="default branch" />
                </label>
                <button type="submit" className="primary" disabled={!info.data?.jobs.enabled}>
                  Analyze
                </button>
              </form>
            ) : (
              <div className="dropzone">
                <label htmlFor="zip-input">ZIP archive</label>
                <input
                  id="zip-input"
                  type="file"
                  accept=".zip,application/zip"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) start(apiUpload<Job>("jobs/zip", { name: file.name }, file));
                  }}
                />
                <span className="muted">Path-traversal and zip-bomb protected · symlinks ignored</span>
              </div>
            )}
          </section>
          <LimitsPanel limits={info.data?.jobs.limits ?? null} />
        </div>
        <div className="import-right">
          {error && <ErrorState error={error} onRetry={reset} />}
          {job && progressing && (
            <section className="panel">
              <div className="label">Analysis progress</div>
              <ol className="stages" data-testid="stages">
                {STAGES.map(([stage, label], i) => {
                  const state =
                    job.stage === stage
                      ? "active"
                      : i < reached || seen.includes(stage) || job.stage === "done"
                        ? "done"
                        : "todo";
                  return (
                    <li key={stage} className={state}>
                      {label}
                    </li>
                  );
                })}
              </ol>
            </section>
          )}
          {job?.stage === "failed" && job.error && (
            <div className="panel error-state" role="alert">
              <strong>Analysis failed</strong>
              <p>{`${job.error.kind}: ${job.error.message}`}</p>
              <button type="button" onClick={reset}>
                Try again
              </button>
            </div>
          )}
          {done && (
            <section className="panel">
              <div className="label">Snapshot</div>
              <p>
                {done.repository} @ <span className="mono accent">{shortSnapshot(done.snapshot)}</span> · pinned,
                reproducible
              </p>
              <Link
                className="button primary"
                to={toPath({ ...DEFAULT, repository: done.repository, snapshot: done.snapshot })}
              >
                Open graph
              </Link>
            </section>
          )}
          {done && <Coverage repository={done.repository} snapshot={done.snapshot} />}
        </div>
      </div>
    </div>
  );
}
