import { nodeName } from "./names";

import type { Item } from "@/api/types";

/** Linked files with the confidence of each link; externals are not clickable. */
export function ItemLinks({
  items,
  onOpen,
  testId,
}: {
  items: Item[] | undefined;
  onOpen: (node: string) => void;
  testId?: string;
}) {
  // while the answer is on its way nothing is claimed, not even "none"
  if (items === undefined) return <p className="muted">loading…</p>;
  return (
    <ul className="rows" data-testid={testId}>
      {items.map((i) => (
        <li key={i.node}>
          {i.node.startsWith("file:") ? (
            <button type="button" className="link mono" onClick={() => onOpen(i.node)}>
              {nodeName(i.node)}
            </button>
          ) : (
            <span className="mono">{nodeName(i.node)}</span>
          )}
          <span className={`pill ${i.kind === "external" ? "" : i.confidence}`}>
            {i.kind === "external" ? "external" : i.confidence}
          </span>
        </li>
      ))}
      {items.length === 0 && <li className="muted">none</li>}
    </ul>
  );
}
