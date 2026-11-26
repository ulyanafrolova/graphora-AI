import axios from "axios";

const API = "/v1";

export function getOrder(id: string) {
  return fetch(`${API}/orders/${id}`);
}

export function adminStats() {
  return axios.get("/admin/stats");
}

export function dailyReport() {
  return fetch("/reports/daily");
}

export function oldDailyReport() {
  return fetch("/old/daily");
}
