import type { Edge } from "@/api/types";
import { nodeName } from "@/graph/names";
import { shortSnapshot } from "@/shell/Header";

export function ProvenancePanel({ edge }: { edge: Edge }) {
  const source = nodeName(edge.source);
  return (
    <section className="panel provenance" data-testid="provenance">
      <div className="label">Edge provenance</div>
      <p className="mono">{`${source} → ${nodeName(edge.target)}`}</p>
      <dl>
        <dt>type</dt>
        <dd className="mono">{edge.symbol ? `${edge.type} · ${edge.symbol}` : edge.type}</dd>
        <dt>source</dt>
        <dd className="mono">{`${source}:${edge.line}@${shortSnapshot(edge.snapshot)}`}</dd>
        <dt>confidence</dt>
        <dd>
          <span className={`pill ${edge.confidence}`}>{edge.confidence}</span>
        </dd>
        <dt>extractor</dt>
        <dd className="mono">{edge.extractor}</dd>
        <dt>snippet hash</dt>
        <dd className="mono">{edge.snippet_hash}</dd>
      </dl>
    </section>
  );
}
