import type { Answer } from "@/api/types";
import { nodeName } from "@/graph/names";
import { PathLabel } from "@/shell/PathLabel";

export function TopRisks({ answer, onOpen }: { answer: Answer; onOpen?: (node: string) => void }) {
  return (
    <table className="risks">
      <colgroup>
        <col />
        <col className="num" />
        <col className="num" />
        <col className="num" />
      </colgroup>
      <thead>
        <tr>
          <th>File</th>
          <th>Commits</th>
          <th>Used by</th>
          <th>Bus factor</th>
        </tr>
      </thead>
      <tbody>
        {(answer.items ?? []).slice(0, 10).map((i) => {
          const path = nodeName(i.node);
          return (
            <tr key={i.node}>
              <td className="file">
                <button
                  type="button"
                  className="link mono"
                  title={path}
                  aria-label={path}
                  onClick={() => onOpen?.(i.node)}
                >
                  <PathLabel path={path} />
                </button>
              </td>
              <td>{i.commits}</td>
              <td>{i.transitive_dependents}</td>
              <td>
                <span className={`pill ${i.authors === 1 ? "cycle" : i.authors === 2 ? "heuristic" : "resolved"}`}>
                  {i.authors}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
