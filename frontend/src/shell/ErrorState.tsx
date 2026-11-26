import { Link } from "react-router";

import type { ApiError } from "@/api/client";

interface Shown {
  title: string;
  hint?: string;
  action: "retry" | "import";
}

function describe(error: ApiError): Shown {
  switch (error.kind) {
    case "network":
    case "store_unavailable":
      return { title: "Graphora service unavailable", hint: "Is graphora serve running?", action: "retry" };
    case "not_found":
      return { title: "Snapshot not found", action: "import" };
    case "stale":
      return { title: "Analyzed with an older version — analyze again", action: "import" };
    case "busy":
      return {
        title: "Another question is being answered",
        hint: error.retryAfter !== null ? `try again in ${error.retryAfter} s` : "try again soon",
        action: "retry",
      };
    case "model_unavailable":
      return { title: "Model not available", hint: "Start it with: ollama serve", action: "retry" };
    case "too_many_jobs":
      return { title: "Too many analyses queued, try later", action: "retry" };
    default:
      return { title: "Something went wrong", action: "retry" };
  }
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const shown = describe(error);
  return (
    <div className="panel error-state" role="alert">
      <strong>{shown.title}</strong>
      {shown.hint !== undefined && <p className="muted">{shown.hint}</p>}
      <p className="muted mono">{error.message}</p>
      {shown.action === "import" ? (
        <Link to="/import">Import</Link>
      ) : (
        onRetry !== undefined && (
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        )
      )}
    </div>
  );
}
