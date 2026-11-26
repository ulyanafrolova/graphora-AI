export function calls(url: string, buildUrl: () => string, m: string) {
  fetch(url);
  fetch(buildUrl());
  fetch("/health");
  fetch("/nowhere");
  fetch("https://api.github.com/repos");
  return fetch("/api/items", { method: m });
}
