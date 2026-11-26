// Thin client for the FastAPI backend. All requests go to this origin's /api/v1 (proxied).

export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  status: number;
  code: string;
  details?: FieldError[];

  constructor(status: number, code: string, message: string, details?: FieldError[]) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const d of this.details ?? []) if (d.field && !out[d.field]) out[d.field] = d.message;
    return out;
  }
}

// Errors that mean "send the user somewhere else" rather than "show a message".
export const GATE_CODES = new Set([
  "password_change_required",
  "mfa_enrolment_required",
  "organisation_not_found",
]);
export const GATE_EVENT = "smecm:gate";

let activeOrgId: string | null = null;
export function setActiveOrgId(id: string | null) {
  activeOrgId = id;
}
export function getActiveOrgId() {
  return activeOrgId;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>;

export type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  /** Send X-Organisation-Id (default true). */
  org?: boolean;
  /** Skip the silent refresh-and-retry on 401. */
  noRefresh?: boolean;
  /** Multipart body (file uploads); sent instead of a JSON body. */
  form?: FormData;
};

function buildUrl(path: string, query?: Query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.set(key, String(value));
  }
  const qs = params.toString();
  return `/api/v1${path}${qs ? `?${qs}` : ""}`;
}

let refreshing: Promise<boolean> | null = null;
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      setTimeout(() => (refreshing = null), 0);
    });
  return refreshing;
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const data = await res.json();
    if (data?.error) {
      return new ApiError(res.status, data.error.code, data.error.message, data.error.details);
    }
  } catch {
    /* fall through */
  }
  return new ApiError(res.status, "http_error", "Something went wrong. Please try again.");
}

async function request(path: string, options: RequestOptions): Promise<Response> {
  const { method = "GET", body, query, org = true, noRefresh = false, form } = options;
  const send = () => {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined && !form) headers["Content-Type"] = "application/json";
    const csrf = readCookie("smecm_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
    if (org && activeOrgId) headers["X-Organisation-Id"] = activeOrgId;
    return fetch(buildUrl(path, query), {
      method,
      headers,
      credentials: "same-origin",
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  };

  let res: Response;
  try {
    res = await send();
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection.");
  }
  if (res.status === 401 && !noRefresh) {
    const err = await toError(res.clone());
    if (err.code === "session_expired" || err.code === "not_authenticated") {
      if (await refreshSession()) res = await send();
    }
  }
  if (!res.ok) {
    const err = await toError(res);
    if (GATE_CODES.has(err.code) && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(GATE_EVENT, { detail: err.code }));
    }
    throw err;
  }
  return res;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await request(path, options);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Download an authenticated file (it needs our headers, so a plain link won't do). */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await request(path, { method: "GET" });
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}
