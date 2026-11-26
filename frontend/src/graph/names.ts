export function nodeName(id: string): string {
  if (id.startsWith("file:")) return id.slice(5);
  if (id.startsWith("ext:")) return id.split(":").slice(2).join(":");
  return id.replace(/^[a-z]+:/, "");
}

const LABEL_MAX = 32;

/** The end of a long component name for the graph; the panel shows the whole name. */
export function componentLabel(name: string): string {
  const [path = "", suffix = ""] = name.split(/(?= · \d+$)/);
  if (path.length <= LABEL_MAX) return name;
  const parts = path.split("/");
  let tail = parts.pop() ?? "";
  while (parts.length > 0 && `…/${parts[parts.length - 1]}/${tail}`.length <= LABEL_MAX)
    tail = `${parts.pop()}/${tail}`;
  return parts.length > 0 ? `…/${tail}${suffix}` : `${tail}${suffix}`;
}
