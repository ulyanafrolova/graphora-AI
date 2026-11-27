/** 12345 → "12 345"; "…" while the number is not known yet. */
export function thousands(n: number | undefined): string {
  return n === undefined ? "…" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}
