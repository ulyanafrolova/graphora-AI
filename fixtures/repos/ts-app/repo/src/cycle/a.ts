import { cycleB } from "./b";

export function cycleA(): number {
  return cycleB() + 1;
}
