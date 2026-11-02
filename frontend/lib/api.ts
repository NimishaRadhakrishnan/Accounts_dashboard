// Thin fetch wrapper. Session lives in httpOnly cookies; every write carries the CSRF header.

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const HEADERS = { "X-Requested-With": "vbt-accounts" };
let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", headers: HEADERS, credentials: "same-origin" })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => setTimeout(() => (refreshing = null), 0));
  }
  return refreshing;
}

async function errorFrom(res: Response): Promise<ApiError> {
  let msg = `Something went wrong (${res.status}).`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") msg = body.detail;
  } catch {
    /* not JSON */
  }
  return new ApiError(msg, res.status);
}

type Opts = { method?: string; body?: unknown; form?: FormData; retry?: boolean };

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const init: RequestInit = { method: opts.method ?? "GET", credentials: "same-origin", headers: { ...HEADERS } };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (res.status === 401 && opts.retry !== false && !path.startsWith("/api/auth/")) {
    if (await tryRefresh()) return api<T>(path, { ...opts, retry: false });
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
  }
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as T;
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body ?? {} });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** Download a file from the API (Excel / PDF / XML) and hand it to the browser. */
export async function download(path: string, fallbackName: string): Promise<void> {
  let res = await fetch(path, { credentials: "same-origin", headers: HEADERS });
  if (res.status === 401 && (await tryRefresh())) res = await fetch(path, { credentials: "same-origin", headers: HEADERS });
  if (!res.ok) throw await errorFrom(res);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Open a PDF in a new tab (invoices). */
export async function openPdf(path: string): Promise<void> {
  const win = window.open("", "_blank");
  const res = await fetch(path, { credentials: "same-origin", headers: HEADERS });
  if (!res.ok) {
    win?.close();
    throw await errorFrom(res);
  }
  const url = URL.createObjectURL(await res.blob());
  if (win) win.location.href = url;
  else window.location.href = url;
}
