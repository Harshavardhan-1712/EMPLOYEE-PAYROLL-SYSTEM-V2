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
let csrfInitialization: Promise<void> | null = null;

export function setCsrfToken(token: string): void {
  csrfTokenValue = token;
}

export function clearCsrfToken(): void {
  csrfTokenValue = "";
  csrfInitialization = null;
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

/**
 * Restore CSRF token from the authenticated backend session.
 */
export async function initializeCsrf(force = false): Promise<void> {
  if (csrfTokenValue && !force) {
    console.log("[CSRF] Token already initialized.");
    return;
  }

  if (csrfInitialization) {
    return csrfInitialization;
  }

  csrfInitialization = (async () => {
    console.log("[CSRF] Requesting token from backend...");

    const response = await fetch(`${BASE}/api/auth/csrf`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      credentials: "include",
    });

    console.log("[CSRF] Initialization response:", response.status);

    if (!response.ok) {
      if (response.status === 401) {
        clearCsrfToken();
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      }

      throw new ApiError(
        response.status,
        "csrf_initialization_failed",
        "Unable to restore CSRF token. Please log in again."
      );
    }

    const data = (await response.json()) as CsrfResponse;

    if (!data.csrf_token || typeof data.csrf_token !== "string") {
      throw new ApiError(
        403,
        "csrf_token_missing",
        "The backend did not return a valid CSRF token."
      );
    }

    setCsrfToken(data.csrf_token);

    console.log("[CSRF] Token successfully stored:", {
      available: Boolean(csrfTokenValue),
      length: csrfTokenValue.length,
    });
  })();

  try {
    await csrfInitialization;
  } finally {
    csrfInitialization = null;
  }
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
  const isLogout = path.startsWith("/auth/logout");

  if (unsafe && !isLogin && !isLogout) {
    if (!csrfTokenValue) {
      console.log("[CSRF] Token missing. Initializing automatically...");
      await initializeCsrf();
    }

    if (!csrfTokenValue) {
      throw new ApiError(
        403,
        "csrf_token_missing",
        "CSRF token is missing. Please log in again."
      );
    }

    headers["X-CSRF-Token"] = csrfTokenValue;
  }

  // Diagnostic logging: never print the actual token.
  console.log("[API REQUEST DEBUG]", {
    url: `${BASE}/api${path}`,
    method,
    csrfTokenAvailable: Boolean(csrfTokenValue),
    csrfTokenLength: csrfTokenValue.length,
    csrfHeaderPresent: Boolean(headers["X-CSRF-Token"]),
    csrfHeaderLength: headers["X-CSRF-Token"]?.length ?? 0,
  });

  let res: Response;

  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers,
      body,
      signal: opts.signal,
      credentials: "include",
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") {
      throw error;
    }

    throw new ApiError(
      0,
      "network_error",
      "Could not reach the server. Check your connection and try again."
    );
  }

  if (res.status === 204) {
    if (isLogout) clearCsrfToken();
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

    console.error("[API ERROR]", {
      path,
      status: res.status,
      response: payload,
    });

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

  if (isLogout) clearCsrfToken();

  return data as T;
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