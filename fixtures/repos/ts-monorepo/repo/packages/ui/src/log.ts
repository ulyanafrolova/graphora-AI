import type { Level } from "./types";

export class Log {
  write(level: Level, message: string): void {}
}

function format(message: string): string {
  return message.trim();
}

export { format as fmt2 };
