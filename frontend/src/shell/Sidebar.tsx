import { Link, NavLink } from "react-router";

import { DEFAULT, toPath, type RouteState, type Screen } from "@/state/route";

const SECTIONS: { title: string; items: { label: string; screen: Screen | "import" }[] }[] = [
  {
    title: "Project",
    items: [
      { label: "Import", screen: "import" },
      { label: "Dependency graph", screen: "graph" },
      { label: "Code & provenance", screen: "code" },
    ],
  },
  {
    title: "AI agents",
    items: [
      { label: "Ask agents", screen: "ask" },
      { label: "Agent trace", screen: "trace" },
    ],
  },
  {
    title: "Insights",
    items: [
      { label: "Cycles", screen: "cycles" },
      { label: "Hotspots", screen: "hotspots" },
      { label: "PR impact", screen: "pr-impact" },
      { label: "Security", screen: "security" },
    ],
  },
  { title: "Integrations", items: [{ label: "MCP for agents", screen: "mcp" }] },
];

export function Sidebar({ route, current }: { route: RouteState | null; current: Screen | null }) {
  return (
    <aside className="sidebar">
      <nav>
        {SECTIONS.map((section) => (
          <div key={section.title} className="section">
            <div className="label">{section.title}</div>
            {section.items.map(({ label, screen }) => {
              if (screen === "import") {
                return (
                  <NavLink key={label} to="/import" className="item">
                    {label}
                  </NavLink>
                );
              }
              if (route === null) {
                return (
                  <span key={label} className="item disabled">
                    {label}
                  </span>
                );
              }
              const to = toPath({ ...DEFAULT, repository: route.repository, snapshot: route.snapshot, screen });
              return (
                <Link key={label} to={to} className="item" aria-current={current === screen ? "page" : undefined}>
                  {label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <p className="footnote">
        Code is never executed.
        <br />
        Read-only agents.
      </p>
    </aside>
  );
}
