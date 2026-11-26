// The page address is the UI state (specs/019-frontend data-model.md § Route state).

export const SCREENS = ["graph", "code", "ask", "trace", "cycles", "hotspots", "pr-impact", "security", "mcp"] as const;
export type Screen = (typeof SCREENS)[number];
export const LEVELS = ["system", "component", "file"] as const;
export type Level = (typeof LEVELS)[number];
export const HIDDEN = ["external", "tests"] as const;
export type Hidden = (typeof HIDDEN)[number];

export interface RouteState {
  repository: string;
  snapshot: string;
  screen: Screen;
  level: Level;
  component: string | null;
  node: string | null;
  impact: boolean;
  hide: Hidden[];
  path: string | null;
  line: number | null;
  group: number | null;
  run: string | null;
}

export const DEFAULT: RouteState = {
  repository: "",
  snapshot: "",
  screen: "graph",
  level: "system",
  component: null,
  node: null,
  impact: false,
  hide: [],
  path: null,
  line: null,
  group: null,
  run: null,
};

const LAST = "graphora.last";

function positive(value: string | null): number | null {
  return value !== null && /^[1-9][0-9]{0,8}$/.test(value) ? Number(value) : null;
}

function decode(segment: string): string | null {
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

export function parseRoute(pathname: string, search: string): RouteState | null {
  const parts = pathname.split("/");
  if (parts.length !== 5 || parts[0] !== "" || parts[1] !== "r") return null;
  const [repository, snapshot, screen] = [decode(parts[2] ?? ""), decode(parts[3] ?? ""), parts[4] ?? ""];
  if (!repository || !snapshot || !(SCREENS as readonly string[]).includes(screen)) return null;
  const q = new URLSearchParams(search);
  const level = q.get("level");
  const hide = (q.get("hide") ?? "").split(",").filter((h): h is Hidden => (HIDDEN as readonly string[]).includes(h));
  return {
    ...DEFAULT,
    repository,
    snapshot,
    screen: screen as Screen,
    level: level !== null && (LEVELS as readonly string[]).includes(level) ? (level as Level) : "system",
    component: q.get("component"),
    node: q.get("node"),
    impact: q.get("impact") === "on",
    hide: [...new Set(hide)].sort(),
    path: q.get("path"),
    line: positive(q.get("line")),
    group: positive(q.get("group")),
    run: q.get("run"),
  };
}

export function toPath(state: RouteState): string {
  const base = `/r/${encodeURIComponent(state.repository)}/${encodeURIComponent(state.snapshot)}/${state.screen}`;
  const q: [string, string][] = [];
  if (state.level !== "system") q.push(["level", state.level]);
  if (state.component !== null) q.push(["component", state.component]);
  if (state.node !== null) q.push(["node", state.node]);
  if (state.impact) q.push(["impact", "on"]);
  if (state.hide.length) q.push(["hide", [...state.hide].sort().join(",")]);
  if (state.path !== null) q.push(["path", state.path]);
  if (state.line !== null) q.push(["line", String(state.line)]);
  if (state.group !== null) q.push(["group", String(state.group)]);
  if (state.run !== null) q.push(["run", state.run]);
  const query = q.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  return query ? `${base}?${query}` : base;
}

export function switchSnapshot(
  state: RouteState,
  repository: string,
  snapshot: string,
  hasNode: (id: string) => boolean,
): { state: RouteState; note: string | null } {
  const keep = state.node !== null && hasNode(state.node);
  return {
    state: { ...state, repository, snapshot, level: "system", component: null, impact: false, node: keep ? state.node : null, group: null, run: null },
    note: state.node !== null && !keep ? "selection cleared: not in this snapshot" : null,
  };
}

export function rememberSnapshot(repository: string, snapshot: string): void {
  try {
    localStorage.setItem(LAST, JSON.stringify({ repository, snapshot }));
  } catch {
    // storage unavailable
  }
}

export function lastSnapshot(): { repository: string; snapshot: string } | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(LAST) ?? "null");
    const v = value as { repository?: unknown; snapshot?: unknown } | null;
    return v && typeof v.repository === "string" && typeof v.snapshot === "string"
      ? { repository: v.repository, snapshot: v.snapshot }
      : null;
  } catch {
    return null;
  }
}
