// Code colouring as tokens, never HTML; JavaScript regex engine, no WASM (research R1, R12).
import type { HighlighterCore } from "shiki/core";

export interface Token {
  content: string;
  color?: string | undefined;
}

const LANGS: Record<string, string> = {
  py: "python",
  pyi: "python",
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  cs: "csharp",
};
let highlighter: Promise<HighlighterCore> | null = null;

function load(): Promise<HighlighterCore> {
  highlighter ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] = await Promise.all([
      import("shiki/core"),
      import("shiki/engine/javascript"),
    ]);
    return createHighlighterCore({
      engine: createJavaScriptRegexEngine(),
      themes: [import("shiki/themes/github-dark-default.mjs")],
      langs: [
        import("shiki/langs/python.mjs"),
        import("shiki/langs/typescript.mjs"),
        import("shiki/langs/tsx.mjs"),
        import("shiki/langs/javascript.mjs"),
        import("shiki/langs/jsx.mjs"),
        import("shiki/langs/csharp.mjs"),
      ],
    });
  })();
  return highlighter;
}

export function language(path: string): string | null {
  return LANGS[path.slice(path.lastIndexOf(".") + 1).toLowerCase()] ?? null;
}

export async function tokenize(path: string, code: string): Promise<Token[][] | null> {
  const lang = language(path);
  if (lang === null) return null;
  try {
    const h = await load();
    return h
      .codeToTokens(code, { lang, theme: "github-dark-default" })
      .tokens.map((line) => line.map((t) => ({ content: t.content, color: t.color })));
  } catch {
    return null;
  }
}
