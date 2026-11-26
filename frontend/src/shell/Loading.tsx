export function Loading({ what }: { what: string }) {
  return (
    <p className="muted" role="status">
      Loading {what}…
    </p>
  );
}

export function Empty({ children }: { children: string }) {
  return <p className="muted empty">{children}</p>;
}
