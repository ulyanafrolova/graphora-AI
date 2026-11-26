import type { Answer } from "@/api/types";
import { nodeName } from "@/graph/names";

export function TopRisks({ answer, onOpen }: { answer: Answer; onOpen?: (node: string) => void }) {
  return (
    <table className="risks">
      <thead>
        <tr>
          <th>File</th>
          <th>Commits</th>
          <th>Used by</th>
          <th>Bus factor</th>
        </tr>
      </thead>
      <tbody>
        {(answer.items ?? []).slice(0, 10).map((i) => (
          <tr key={i.node}>
            <td>
              <button type="button" className="link mono" onClick={() => onOpen?.(i.node)}>
                {nodeName(i.node)}
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
        ))}
      </tbody>
    </table>
  );
}
