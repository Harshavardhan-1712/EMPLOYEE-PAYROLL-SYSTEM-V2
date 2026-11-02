
import type { ApiErrorDetail } from "./types";

const BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: ApiErrorDetail[] = []
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const AUTH_EXPIRED_EVENT = "pv2:auth-expired";

let csrfTokenValue = "";

export function setCsrfToken(token: string): void {
  csrfTokenValue = token;
}

export function clearCsrfToken(): void {
  csrfTokenValue = "";
}

interface Opts {
  method?: string;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

interface CsrfResponse {
  csrf_token?: string;
}

export async function api<T>(
  path: string,
  opts: Opts = {}
): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...opts.headers,
  };

  let body: BodyInit | undefined;

  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const unsafe = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  const isLogin = path.startsWith("/auth/login");

  if (unsafe && csrfTokenValue) {
    headers["X-CSRF-Token"] = csrfTokenValue;
  } else if (unsafe && !isLogin && !path.startsWith("/auth/logout")) {
    throw new ApiError(
      403,
      "csrf_token_missing",
      "CSRF token is missing. Please restore your session and try again."
    );
  }

  let res: Response;

  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers,
      body,
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;

    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server. Check your connection and try again."
    );
  }

  if (res.status === 204) {
    if (path.startsWith("/auth/logout")) {
      clearCsrfToken();
    }
    return undefined as T;
  }

  let data: unknown = null;

  try {
    data = await res.json();
  } catch {
    // Response may not contain JSON.
  }

  if (!res.ok) {
    const payload = data as {
      error?: {
        code?: string;
        message?: string;
        details?: ApiErrorDetail[];
      };
      detail?: string;
    } | null;

    if (res.status === 401 && !isLogin) {
      clearCsrfToken();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }

    throw new ApiError(
      res.status,
      payload?.error?.code ?? "error",
      payload?.error?.message ??
        payload?.detail ??
        `Request failed (${res.status})`,
      payload?.error?.details ?? []
    );
  }

  const responseData = data as CsrfResponse | null;

  if (
    responseData?.csrf_token &&
    typeof responseData.csrf_token === "string"
  ) {
    setCsrfToken(responseData.csrf_token);
  }

  if (path.startsWith("/auth/logout")) {
    clearCsrfToken();
  }

  return data as T;
}

/**
 * Restore the CSRF token from the authenticated session.
 * Call before protected POST, PUT, PATCH or DELETE requests
 * if the page has been refreshed.
 */
export async function initializeCsrf(): Promise<void> {
  const result = await api<CsrfResponse>("/auth/csrf");

  if (!result?.csrf_token) {
    throw new ApiError(
      403,
      "csrf_token_missing",
      "Unable to restore the CSRF token. Please log in again."
    );
  }

  setCsrfToken(result.csrf_token);
}

export function qs(
  params: Record<string, string | number | undefined | null>
): string {
  const u = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      u.set(key, String(value));
    }
  }

  const result = u.toString();
  return result ? `?${result}` : "";
}

/** Same-origin URL for direct browser navigation (PDF preview / download). */
export const apiUrl = (path: string) => `${BASE}/api${path}`;
