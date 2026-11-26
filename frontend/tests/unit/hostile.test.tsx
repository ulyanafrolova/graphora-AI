// SC-004: repository and model text is shown literally, never as markup or links (research R12).
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { expect, test } from "vitest";

import { ApiError } from "@/api/client";
import type { Edge } from "@/api/types";
import { CodeView } from "@/code/CodeView";
import { ProvenancePanel } from "@/code/ProvenancePanel";
import { ErrorState } from "@/shell/ErrorState";
import { Header } from "@/shell/Header";
import { Path } from "@/shell/Path";

export const HOSTILE = [
  "<script>alert(1)</script>",
  "<img src=x onerror=alert(1)>",
  "javascript:alert(1)",
  "**md**",
  "[a](javascript:x)",
];

// Later phases add their screens here.
export const SCREENS: [string, (text: string) => ReactElement][] = [
  ["Path", (t) => <Path value={t} line={3} />],
  ["Header", (t) => <Header repository={t} snapshot="content:0123456789abcdef" files={[]} ask={null} />],
  ["ErrorState", (t) => <ErrorState error={new ApiError(404, "not_found", t)} />],
  [
    "CodeView",
    (t) => (
      <CodeView
        lines={{ path: "a.txt", has_text: true, line_count: 1, start: 1, end: 1, lines: [{ n: 1, text: t }] }}
        markers={new Map()}
        selected={null}
        onSelect={() => undefined}
      />
    ),
  ],
  [
    "ProvenancePanel",
    (t) => (
      <ProvenancePanel
        edge={
          {
            id: "e",
            source: `file:${t}`,
            target: "file:b.py",
            line: 1,
            symbol: t,
            type: "imports",
            confidence: "resolved",
            extractor: t,
            snippet_hash: t,
            snapshot: "content:1",
          } as unknown as Edge
        }
      />
    ),
  ],
];

test.each(SCREENS.flatMap(([name, make]) => HOSTILE.map((text) => [name, make, text] as const)))(
  "%s shows %#",
  (_, make, text) => {
    const { container } = render(<MemoryRouter>{make(text)}</MemoryRouter>);
    expect(container.querySelector("script, img, iframe, object, embed")).toBeNull();
    for (const a of container.querySelectorAll("a")) expect(a.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
    expect(container.textContent).toContain(text);
  },
);
