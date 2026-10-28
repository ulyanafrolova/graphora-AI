export type Shape = { w: number; h: number };

export function area(s: Shape): number {
  return s.w * s.h;
}
