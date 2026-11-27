import type { ReactNode } from "react";

import type { CoverageFile } from "@/api/graph.gen";

const NAMES: Record<string, string> = {
  python: "Python",
  typescript: "TypeScript",
  javascript: "JavaScript",
  csharp: "C#",
  fsharp: "F#",
  vbnet: "VB.NET",
  cpp: "C++",
  c: "C",
  go: "Go",
  razor: "Razor",
};

export function languageName(language: string): string {
  return NAMES[language] ?? language.charAt(0).toUpperCase() + language.slice(1);
}

export function shortSnapshot(id: string): string {
  if (id.startsWith("content:")) return id.slice(0, "content:".length + 8);
  const dirty = id.indexOf("+dirty:");
  return dirty >= 0 ? `${id.slice(0, 7)}+dirty` : id.slice(0, 7);
}

export interface LanguageBadge {
  language: string;
  status: "analyzed" | "detected only";
}

export function languageBadges(files: CoverageFile[]): LanguageBadge[] {
  const analyzed = new Set<string>();
  const seen = new Set<string>();
  for (const f of files) {
    if (f.language === null || f.status === "not_code") continue;
    seen.add(f.language);
    if (f.status === "analyzed") analyzed.add(f.language);
  }
  return [...seen]
    .map((language): LanguageBadge => ({
      language: languageName(language),
      status: analyzed.has(language) ? "analyzed" : "detected only",
    }))
    .sort((a, b) => (a.status === b.status ? a.language.localeCompare(b.language) : a.status === "analyzed" ? -1 : 1));
}

export function modelBadge(ask: { enabled: boolean; model: string | null }): string {
  if (!ask.enabled || ask.model === null) return "agents off";
  const [provider, ...rest] = ask.model.split(":");
  const model = rest.join(":");
  return provider === "ollama" ? `${model} · local` : `${model} · ${provider}`;
}

export interface HeaderProps {
  repository: string | null;
  snapshot: string | null;
  files: CoverageFile[];
  ask: { enabled: boolean; model: string | null } | null;
  picker?: ReactNode;
}

export function Header({ repository, snapshot, files, ask, picker }: HeaderProps) {
  return (
    <header className="header">
      <span className="brand">
        graph<span>ora</span>
      </span>
      {picker ??
        (repository !== null && snapshot !== null && (
          <span className="snapshot mono" title={`${repository} @ ${snapshot}`}>
            <span className="repo">{repository}</span> <span className="at">@</span>{" "}
            <span>{shortSnapshot(snapshot)}</span>
          </span>
        ))}
      <span className="badges">
        {languageBadges(files).map((b) => (
          <span key={b.language} className={`pill ${b.status === "analyzed" ? "analyzed" : "detected"}`}>
            {`${b.language} · ${b.status}`}
          </span>
        ))}
        {ask !== null && <span className="pill accent">{modelBadge(ask)}</span>}
      </span>
    </header>
  );
}
