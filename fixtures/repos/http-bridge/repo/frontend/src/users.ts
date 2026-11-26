export function getUser(id: number) {
  return fetch(`/users/${id}`);
}

export function getMe() {
  return fetch("/users/me");
}

export function getOrders(id: number) {
  return fetch("/users/" + id + "/orders");
}

export function getLegacyUser(id: number) {
  return fetch(`/legacy/users/${id}`);
}

export function deleteLegacyUser(id: number) {
  return fetch(`/legacy/users/${id}`, { method: "DELETE" });
}

export function getMeWithQuery() {
  return fetch("/users/me?fields=name");
}
