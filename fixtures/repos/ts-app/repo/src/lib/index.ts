import { cycleA } from "../cycle/a";

export interface Config {
  debug: boolean;
}

export const lib = (): number => cycleA();
