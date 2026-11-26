import "./integrations.css";

import { useInfo } from "@/api/queries";
import type { Info } from "@/api/types";
import { ErrorState } from "@/shell/ErrorState";
import { Loading } from "@/shell/Loading";
import type { RouteState } from "@/state/route";

const BACKEND = "<graphora>/backend";
const DATABASE = "<database url>";

const args = (repository: string, snapshot: string) => [
  "run",
  "--directory",
  BACKEND,
  "graphora",
  "mcp",
  "--repository",
  repository,
  "--snapshot",
  snapshot,
];

export const claudeCommand = (repository: string, snapshot: string) =>
  `claude mcp add graphora -e GRAPHORA_DATABASE_URL=${DATABASE} -- uv ${args(repository, snapshot).join(" ")}`;

export const cursorConfig = (repository: string, snapshot: string) =>
  JSON.stringify(
    {
      mcpServers: {
        graphora: { command: "uv", args: args(repository, snapshot), env: { GRAPHORA_DATABASE_URL: DATABASE } },
      },
    },
    null,
    2,
  );

function Snippet({ title, text, copy }: { title: string; text: string; copy: string }) {
  return (
    <div className="snippet">
      <div className="snippet-head">
        <span className="muted"># {title}</span>
        <button type="button" onClick={() => void navigator.clipboard.writeText(text)}>
          {copy}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

export function McpView({
  repository,
  snapshot,
  tools,
}: {
  repository: string;
  snapshot: string;
  tools: Info["mcp_tools"];
}) {
  return (
    <div className="mcp-page">
      <header className="mcp-head">
        <div>
          <h1>MCP for coding agents</h1>
          <p className="muted">
            Expose this snapshot to Claude Code, Cursor and any MCP-compatible agent: graph answers in one tool call
          </p>
        </div>
        <span className="pill resolved">server · stdio, started by the agent</span>
      </header>
      <div className="mcp-grid">
        <div className="mcp-left">
          <section className="panel">
            <h2 className="label">Connect</h2>
            <Snippet title="Claude Code" text={claudeCommand(repository, snapshot)} copy="Copy Claude Code command" />
            <Snippet
              title="Cursor · .cursor/mcp.json"
              text={cursorConfig(repository, snapshot)}
              copy="Copy Cursor settings"
            />
            <p className="muted small">
              Replace the placeholders with the folder of the Graphora checkout and the URL of its database.
            </p>
          </section>
          <section className="panel">
            <h2 className="label">Exposed tools · read-only</h2>
            <table className="mcp-tools">
              <tbody>
                {tools.map((t) => (
                  <tr key={t.name} data-testid="mcp-tool">
                    <td>
                      <code>{t.name}</code>
                    </td>
                    <td className="muted">{t.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
        <section className="terminal">
          <div className="terminal-head">
            <i />
            <i />
            <i />
            <span>
              {repository} @ {snapshot} · coding agent
            </span>
          </div>
          <div className="terminal-body">
            <p>❯ I want to rewrite this file. What could break?</p>
            <p className="call">
              ● Calling <code>graphora.impact</code>(target=&quot;&lt;path&gt;&quot;)
            </p>
            <p className="call">
              ● Calling <code>graphora.cycles</code>()
            </p>
            <p className="muted">
              Every answer is computed from the stored graph of this snapshot, with file:line provenance for each edge;
              the agent does not need to search the repository.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}

export function McpPage({ route }: { route: RouteState }) {
  const info = useInfo();
  if (info.error) return <ErrorState error={info.error} onRetry={() => void info.refetch()} />;
  if (!info.data) return <Loading what="MCP tools" />;
  return <McpView repository={route.repository} snapshot={route.snapshot} tools={info.data.mcp_tools} />;
}
