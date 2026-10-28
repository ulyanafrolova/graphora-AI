export async function fetchItems(): Promise<unknown> {
  return fetch("/api/items");
}
