import axios from "axios";

export async function loadItems() {
  return fetch("/api/items");
}

export async function addItem(body: unknown) {
  return axios.post("/api/items", body);
}

export async function ping() {
  return fetch("/legacy/ping");
}

export async function reloadItems() {
  return fetch("/api/items");
}
