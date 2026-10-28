import { x } from "./x";

export function add(a: number, b: number): number;
export function add(a: string, b: string): string;
export function add(a: any, b: any): any {
  return a + b;
}

export default function () {
  return 0;
}

export const PI = 3.14;
export { x };
