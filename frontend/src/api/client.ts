const BASE = "/api/v1";

export type Params = Record<string, string | number | boolean | undefined>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly kind: string,
    message: string,
    readonly retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function url(path: string, params: Params = {}): string {
  const query = Object.entries(params)
    .filter((entry): entry is [string, string | number | boolean] => entry[1] !== undefined)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join("&");
  return `${BASE}/${path}${query ? `?${query}` : ""}`;
}

async function failure(response: Response): Promise<ApiError> {
  const retry = response.headers.get("Retry-After");
  const retryAfter = retry !== null && /^\d+$/.test(retry) ? Number(retry) : null;
  try {
    const body: unknown = await response.json();
    const error = (body as { error?: { kind?: unknown; message?: unknown } }).error;
    if (error && typeof error.kind === "string" && typeof error.message === "string") {
      return new ApiError(response.status, error.kind, error.message, retryAfter);
    }
  } catch {
    // not the error shape
  }
  return new ApiError(response.status, `http_${response.status}`, response.statusText || "request failed", retryAfter);
}

export async function request(input: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch {
    throw new ApiError(0, "network", "Graphora service unavailable");
  }
  if (!response.ok) throw await failure(response);
  return response;
}

export async function apiGet<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  return (await (await request(url(path, params), signal ? { signal } : {})).json()) as T;
}

export async function apiPost<T>(path: string, body: unknown, params: Params = {}): Promise<T> {
  const init = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  return (await (await request(url(path, params), init)).json()) as T;
}

export async function apiUpload<T>(path: string, params: Params, data: Blob): Promise<T> {
  const init = { method: "POST", headers: { "Content-Type": "application/zip" }, body: data };
  return (await (await request(url(path, params), init)).json()) as T;
}
