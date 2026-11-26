/** Typed HTTP client for ULTRON OS 2026 Backend API — zero mock data, automatic token refresh, single-flight concurrency, and strict auth handling. */

const TOKEN_KEY = "ultron_access_token";
const REFRESH_TOKEN_KEY = "ultron_refresh_token";
const EXPIRES_AT_KEY = "ultron_access_expires_at";
const USER_KEY = "ultron_user_profile";
export const AUTH_STATE_EVENT = "ultron:auth-state-changed";

/** Centralized production URL for the standalone CARAVAN application. */
export const CARAVAN_DEPLOYED_URL = "https://caravan-juwon2.vercel.app";

export interface AuthUser {
  user_id: string;
  username: string;
  email: string;
  role: string;
  tenant_id: string;
}

export interface GeminiBadgeStatus {
  configured: boolean;
  verified: boolean;
  label: string;
  tone: "success" | "info" | "warn" | "neutral";
}

/**
 * Single shared resolver for Google Gemini provider status across Command Centre, NEON, and Connections.
 * Uses actual backend diagnostics (`geminiDiag`, `/health`, and `/health/ready`) so all screens stay consistent.
 */
export function resolveGeminiProviderStatus(opts: {
  geminiDiag?: any;
  health?: any;
  ready?: any;
}): GeminiBadgeStatus {
  const { geminiDiag, health, ready } = opts;
  const configured = Boolean(
    geminiDiag?.configured ||
      health?.integrations?.providers?.gemini?.configured ||
      health?.integrations?.capabilities?.gemini?.configured ||
      health?.providers?.gemini?.configured ||
      ready?.config?.integrations_configured?.gemini
  );
  const liveInf = geminiDiag?.live_inference;
  const verified = Boolean(
    liveInf?.verified ||
      health?.integrations?.providers?.gemini?.live_verified ||
      health?.integrations?.capabilities?.gemini?.live_verified
  );

  if (liveInf?.status === "LIVE VERIFIED" || (verified && liveInf?.status !== "LIVE VERIFIED WITH FALLBACK")) {
    return { configured: true, verified: true, label: "GEMINI LIVE VERIFIED", tone: "success" };
  }
  if (liveInf?.status === "LIVE VERIFIED WITH FALLBACK") {
    return { configured: true, verified: true, label: "GEMINI LIVE (FALLBACK)", tone: "info" };
  }
  if (configured) {
    return { configured: true, verified: false, label: "GEMINI CONFIGURED", tone: "info" };
  }
  return { configured: false, verified: false, label: "GEMINI UNCONFIGURED", tone: "warn" };
}

function emitAuthStateChanged(user: AuthUser | null, reason?: string): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(AUTH_STATE_EVENT, { detail: { user, reason } }));
  }
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function getStoredExpiresAt(): string | null {
  return localStorage.getItem(EXPIRES_AT_KEY);
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

export function saveSession(
  token: string,
  user: AuthUser,
  refreshToken?: string | null,
  expiresAt?: string | null
): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  if (expiresAt) {
    localStorage.setItem(EXPIRES_AT_KEY, expiresAt);
  }
  emitAuthStateChanged(user, "session_saved");
}

export function clearSession(reason = "logged_out"): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(EXPIRES_AT_KEY);
  localStorage.removeItem(USER_KEY);
  emitAuthStateChanged(null, reason);
}

/**
 * Inspect JWT exp claim or stored expires_at timestamp to detect whether the access token
 * is already expired or within `skewSeconds` of expiring.
 */
export function isAccessTokenExpiredOrExpiring(token: string | null, skewSeconds = 30): boolean {
  if (!token) return true;
  try {
    const parts = token.split(".");
    if (parts.length === 3) {
      const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = b64 + "===".slice((b64.length + 3) % 4);
      const payload = JSON.parse(atob(padded));
      if (typeof payload.exp === "number") {
        const nowSec = Math.floor(Date.now() / 1000);
        return nowSec + skewSeconds >= payload.exp;
      }
    }
  } catch {
    // fall back to stored expires_at
  }
  const storedExp = getStoredExpiresAt();
  if (storedExp) {
    const ts = Date.parse(storedExp);
    if (!Number.isNaN(ts)) {
      return Date.now() + skewSeconds * 1000 >= ts;
    }
  }
  return false;
}

let inflightRefreshPromise: Promise<string | null> | null = null;

/**
 * Single-flight refresh token rotation via `POST /api/v1/auth/refresh`.
 * Because the backend immediately revokes a rotated refresh token, all concurrent
 * callers share this single promise so parallel requests never race to rotate the same token.
 */
export async function refreshAccessTokenSingleFlight(): Promise<string | null> {
  if (inflightRefreshPromise) {
    return inflightRefreshPromise;
  }

  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) {
    return null;
  }

  inflightRefreshPromise = (async () => {
    try {
      const resp = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!resp.ok) {
        return null;
      }
      const data = await resp.json();
      if (!data?.access_token) {
        return null;
      }
      const updatedUser: AuthUser = data.user || getStoredUser() || {
        user_id: "unknown",
        username: "operator",
        email: "",
        role: "OWNER",
        tenant_id: "TENANT-ULTRON-01",
      };
      saveSession(data.access_token, updatedUser, data.refresh_token || refreshToken, data.expires_at || null);
      return data.access_token as string;
    } catch {
      return null;
    } finally {
      inflightRefreshPromise = null;
    }
  })();

  return inflightRefreshPromise;
}

function isAuthPublicEndpoint(path: string): boolean {
  return (
    path.startsWith("/api/v1/auth/login") ||
    path.startsWith("/api/v1/auth/bootstrap-owner") ||
    path.startsWith("/api/v1/auth/refresh") ||
    path.startsWith("/health")
  );
}

async function fetchWithAutoRefresh(
  path: string,
  init: RequestInit,
  customHeaders: Record<string, string> = {}
): Promise<Response> {
  const publicEndpoint = isAuthPublicEndpoint(path);
  let token = getStoredToken();

  // Proactive refresh before dispatching if access token is already expired and we have a refresh token
  if (!publicEndpoint && token && isAccessTokenExpiredOrExpiring(token, 20) && getStoredRefreshToken()) {
    const refreshed = await refreshAccessTokenSingleFlight();
    if (refreshed) {
      token = refreshed;
    }
  }

  const buildHeaders = (bearer: string | null): Record<string, string> => {
    const h: Record<string, string> = { ...customHeaders };
    if (bearer) {
      h["Authorization"] = `Bearer ${bearer}`;
    }
    return h;
  };

  let resp = await fetch(path, {
    ...init,
    headers: buildHeaders(token),
  });

  // Reactive 401 recovery: attempt single-flight refresh or reuse token refreshed by a sibling request
  if (resp.status === 401 && !publicEndpoint) {
    const latestToken = getStoredToken();
    let retryToken: string | null = null;

    if (latestToken && latestToken !== token && !isAccessTokenExpiredOrExpiring(latestToken, 5)) {
      retryToken = latestToken;
    } else if (getStoredRefreshToken()) {
      retryToken = await refreshAccessTokenSingleFlight();
    }

    if (retryToken) {
      resp = await fetch(path, {
        ...init,
        headers: buildHeaders(retryToken),
      });
    }

    if (resp.status === 401) {
      clearSession("session_expired");
    }
  }

  return resp;
}

export async function apiFetch<T = any>(
  path: string,
  options: {
    method?: string;
    body?: any;
    isFormData?: boolean;
    headers?: Record<string, string>;
    signal?: AbortSignal;
  } = {}
): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers || {}) };
  let payload: BodyInit | undefined;
  if (options.body !== undefined) {
    if (options.isFormData) {
      payload = options.body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(options.body);
    }
  }

  const resp = await fetchWithAutoRefresh(
    path,
    {
      method: options.method || "GET",
      body: payload,
      signal: options.signal,
    },
    headers
  );

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

export async function downloadAuthFile(path: string, filename: string): Promise<void> {
  const resp = await fetchWithAutoRefresh(path, { method: "GET" });
  if (!resp.ok) throw new Error(`Download failed (HTTP ${resp.status})`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function fetchAuthBlobUrl(path: string): Promise<string> {
  const resp = await fetchWithAutoRefresh(path, { method: "GET" });
  if (!resp.ok) throw new Error(`Preview failed (HTTP ${resp.status})`);
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

export async function streamNeon(
  prompt: string,
  agentId: string,
  onDelta: (chunk: string) => void,
  onMeta?: (meta: any) => void,
  fileIds?: string[]
): Promise<void> {
  const resp = await fetchWithAutoRefresh(
    "/api/v1/neon/stream",
    {
      method: "POST",
      body: JSON.stringify({
        prompt,
        agent_id: agentId,
        file_ids: fileIds && fileIds.length > 0 ? fileIds : undefined,
        enable_web_research: true,
      }),
    },
    { "Content-Type": "application/json" }
  );
  if (!resp.ok || !resp.body) {
    throw new Error(`Stream failed (HTTP ${resp.status})`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        if (!raw) continue;
        try {
          const parsed = JSON.parse(raw);
          if (currentEvent === "delta" && parsed.text) onDelta(parsed.text);
          if (currentEvent === "metadata" && onMeta) onMeta(parsed);
        } catch {
          // ignore malformed keepalives
        }
      }
    }
  }
}
