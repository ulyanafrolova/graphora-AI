export function Path({ value, line }: { value: string; line?: number }) {
  return <code className="path">{line === undefined ? value : `${value}:${line}`}</code>;
}
