/** Typed HTTP client for ULTRON OS 2026 Backend API — zero mock data, strict auth handling. */

const TOKEN_KEY = "ultron_access_token";
const USER_KEY = "ultron_user_profile";

export interface AuthUser {
  user_id: string;
  username: string;
  email: string;
  role: string;
  tenant_id: string;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function saveSession(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function apiFetch<T = any>(
  path: string,
  options: {
    method?: string;
    body?: any;
    isFormData?: boolean;
    headers?: Record<string, string>;
  } = {}
): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = { ...(options.headers || {}) };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  let payload: BodyInit | undefined;
  if (options.body !== undefined) {
    if (options.isFormData) {
      payload = options.body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(options.body);
    }
  }

  const resp = await fetch(path, {
    method: options.method || "GET",
    headers,
    body: payload,
  });

  if (!resp.ok) {
    let message = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      message = err?.error?.message || err?.detail || message;
    } catch {
      // ignore non-JSON errors
    }
    throw new Error(message);
  }

  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await resp.json()) as T;
  }
  return (await resp.text()) as unknown as T;
}
