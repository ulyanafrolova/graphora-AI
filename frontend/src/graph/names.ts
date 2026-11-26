export function nodeName(id: string): string {
  if (id.startsWith("file:")) return id.slice(5);
  if (id.startsWith("ext:")) return id.split(":").slice(2).join(":");
  return id.replace(/^[a-z]+:/, "");
}
