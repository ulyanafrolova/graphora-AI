import "./integrations.css";

/** PR impact and Security stay in the navigation without sample data (spec FR-020). */
export function NotAvailable({ title }: { title: string }) {
  return (
    <div className="not-available">
      <h1>{title}</h1>
      <p className="muted">This screen is not available in this version of Graphora.</p>
    </div>
  );
}
