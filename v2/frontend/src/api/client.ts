
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

// CSRF token is stored in memory and received from the backend.
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
  csrf_token: string;
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

  // Attach CSRF token to all unsafe requests.
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    if (csrfTokenValue) {
      headers["X-CSRF-Token"] = csrfTokenValue;
    }
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
    if ((e as Error).name === "AbortError") {
      throw e;
    }

    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server. Check your connection and try again."
    );
  }

  if (res.status === 204) {
    return undefined as T;
  }

  let data: unknown = null;

  try {
    data = await res.json();
  } catch {
    // Response has no JSON body.
  }

  if (!res.ok) {
    const err = (
      data as {
        error?: {
          code?: string;
          message?: string;
          details?: ApiErrorDetail[];
        };
      } | null
    )?.error;

    if (res.status === 401 && !path.startsWith("/auth/login")) {
      clearCsrfToken();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }

    throw new ApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? `Request failed (${res.status})`,
      err?.details ?? []
    );
  }

  // Automatically capture CSRF token from login response.
  const responseData = data as CsrfResponse | null;

  if (responseData?.csrf_token) {
    setCsrfToken(responseData.csrf_token);
  }

  // Clear token after logout.
  if (path.startsWith("/auth/logout")) {
    clearCsrfToken();
  }

  return data as T;
}

/**
 * Restore the CSRF token after a browser refresh.
 * Requires a valid authenticated session.
 */
export async function initializeCsrf(): Promise<void> {
  const result = await api<CsrfResponse>("/auth/csrf");

  if (result?.csrf_token) {
    setCsrfToken(result.csrf_token);
  }
}

export function qs(
  params: Record<string, string | number | undefined | null>
): string {
  const u = new URLSearchParams();

  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") {
      u.set(k, String(v));
    }
  }

  const s = u.toString();

  return s ? `?${s}` : "";
}

/** Same-origin URL for direct browser navigation (PDF preview / download). */
export const apiUrl = (path: string) => `${BASE}/api${path}`;
