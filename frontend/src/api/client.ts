const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Websocket URL for an API path. Follows VITE_API_BASE when it is set, and
 * the page's own origin when it is not - which is the container build, where
 * nginx proxies /api and carries the upgrade header through. */
export function wsUrl(path: string): string {
  const base = BASE || window.location.origin;
  return base.replace(/^http/, "ws") + path;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};
