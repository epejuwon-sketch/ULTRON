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

  // If live inference failed or returned an error, report honest failure
  if (
    liveInf?.status === "FAILED" ||
    geminiDiag?.connection_status === "FAILED" ||
    (liveInf?.verified === false && liveInf?.error)
  ) {
    return { configured: Boolean(configured), verified: false, label: "GEMINI FAILED", tone: "warn" };
  }

  if (liveInf?.status === "LIVE VERIFIED" || (verified && liveInf?.status !== "LIVE VERIFIED WITH FALLBACK")) {
    return { configured: true, verified: true, label: "GEMINI LIVE VERIFIED", tone: "success" };
  }
  if (liveInf?.status === "LIVE VERIFIED WITH FALLBACK") {
    return { configured: true, verified: true, label: "GEMINI LIVE (FALLBACK)", tone: "info" };
  }
  if (configured) {
    return { configured: true, verified: false, label: "GEMINI CONFIGURED", tone: "info" };
  }
  return { configured: false, verified: false, label: "GEMINI NOT CONFIGURED", tone: "warn" };
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
let sessionRestorationPromise: Promise<AuthUser | null> | null = null;

export function isSessionRestoring(): boolean {
  return sessionRestorationPromise !== null;
}

export async function waitForSessionRestoration(): Promise<AuthUser | null> {
  if (sessionRestorationPromise) {
    return sessionRestorationPromise;
  }
  const token = getStoredToken();
  const refreshToken = getStoredRefreshToken();
  if (!token || isAccessTokenExpiredOrExpiring(token, 45)) {
    if (refreshToken) {
      return restoreSession();
    }
    return getStoredUser();
  }
  return getStoredUser();
}

/**
 * Coordinate asynchronous session restoration and token rotation on startup or foreground resume.
 * Ensures concurrent requests await valid token resolution rather than firing with stale or missing credentials.
 * Resilient to temporary network interruptions (offline/reconnect/backgrounding) so users are never
 * prematurely kicked out of valid sessions.
 */
export async function restoreSession(): Promise<AuthUser | null> {
  if (sessionRestorationPromise) {
    return sessionRestorationPromise;
  }

  const token = getStoredToken();
  const refreshToken = getStoredRefreshToken();
  const user = getStoredUser();

  if (!token && !refreshToken) {
    return null;
  }

  // If access token is still fresh, immediately return stored user
  if (token && !isAccessTokenExpiredOrExpiring(token, 45)) {
    return user;
  }

  // If token is missing or expired, attempt single-flight refresh
  if (refreshToken) {
    sessionRestorationPromise = (async () => {
      try {
        const refreshedToken = await refreshAccessTokenSingleFlight();
        if (refreshedToken) {
          return getStoredUser();
        }
        // If refresh failed due to offline/network outage but refresh credentials remain intact,
        // do NOT clear session! Return current stored user to preserve state while offline.
        if (getStoredRefreshToken() && user) {
          return user;
        }
        return null;
      } catch {
        return user;
      } finally {
        sessionRestorationPromise = null;
      }
    })();
    return sessionRestorationPromise;
  }

  return user;
}

/**
 * Single-flight refresh token rotation via `POST /api/v1/auth/refresh`.
 * Because the backend immediately revokes a rotated refresh token, all concurrent
 * callers share this single promise so parallel requests never race to rotate the same token.
 * 
 * Security & Reliability Guarantee:
 * - Only genuine server-side revocation (HTTP 401 or 403) clears the local session.
 * - Network failures, server cold-starts (5xx), or temporary connectivity drops preserve the session.
 */
export async function refreshAccessTokenSingleFlight(): Promise<string | null> {
  if (inflightRefreshPromise) {
    return inflightRefreshPromise;
  }

  const refreshToken = getStoredRefreshToken();

  inflightRefreshPromise = (async () => {
    try {
      const resp = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken || "" }),
      });
      if (!resp.ok) {
        // ONLY clear session if server explicitly invalidated or revoked the token (HTTP 401/403)
        // If server returned 5xx or is temporarily degraded, keep session intact
        if (resp.status === 401 || resp.status === 403) {
          clearSession("session_expired");
        }
        return null;
      }
      const data = await resp.json().catch(() => null);
      if (!data?.access_token) {
        return null;
      }
      const existingUser = getStoredUser();
      const updatedUser: AuthUser | null = data.user || existingUser;
      if (!updatedUser) {
        return null;
      }
      saveSession(data.access_token, updatedUser, data.refresh_token || refreshToken, data.expires_at || null);
      return data.access_token as string;
    } catch {
      // Network failure, app backgrounded, or offline:
      // DO NOT clear session! The session credentials remain valid once network is restored.
      return null;
    } finally {
      inflightRefreshPromise = null;
    }
  })();

  return inflightRefreshPromise;
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === TOKEN_KEY || e.key === REFRESH_TOKEN_KEY || e.key === USER_KEY) {
      const u = getStoredUser();
      emitAuthStateChanged(u, "storage_sync");
    }
  });
}

function isAuthPublicEndpoint(path: string): boolean {
  return (
    path.startsWith("/api/v1/auth/login") ||
    path.startsWith("/api/v1/auth/bootstrap-owner") ||
    path.startsWith("/api/v1/auth/refresh") ||
    path.startsWith("/api/v1/auth/register") ||
    path.startsWith("/api/v1/auth/verify-email") ||
    path.startsWith("/api/v1/auth/password-reset") ||
    path.startsWith("/health")
  );
}

async function fetchWithAutoRefresh(
  path: string,
  init: RequestInit,
  customHeaders: Record<string, string> = {}
): Promise<Response> {
  const publicEndpoint = isAuthPublicEndpoint(path);

  // If session restoration is needed or in flight, wait for it before dispatching protected requests
  if (!publicEndpoint) {
    await restoreSession();
  }

  let token = getStoredToken();

  // Proactive refresh before dispatching if access token is missing/expired and we have a refresh token
  if (!publicEndpoint && (!token || isAccessTokenExpiredOrExpiring(token, 30))) {
    const refreshToken = getStoredRefreshToken();
    if (refreshToken) {
      const refreshed = await refreshAccessTokenSingleFlight();
      if (refreshed) {
        token = refreshed;
      } else {
        token = null;
      }
    } else {
      token = null;
    }
  }

  // Guard: if signed out and attempting protected request without valid access token,
  // do not dispatch unauthenticated request over wire with missing Authorization header.
  if (!publicEndpoint && !token) {
    clearSession("reauth_required");
    throw new Error("Active authenticated session required. Please sign in.");
  }

  const buildHeaders = (bearer: string | null): Record<string, string> => {
    const h: Record<string, string> = { ...customHeaders };
    if (bearer && bearer.trim()) {
      const clean = bearer.trim();
      h["Authorization"] = `Bearer ${clean}`;
      h["X-Authorization"] = `Bearer ${clean}`;
      h["X-Ultron-Authorization"] = `Bearer ${clean}`;
    }
    return h;
  };

  let resp: Response;
  try {
    resp = await fetch(path, {
      ...init,
      credentials: "same-origin",
      headers: buildHeaders(token),
    });
  } catch (netErr: any) {
    if (netErr?.name === "TypeError" && /load failed|failed to fetch/i.test(netErr?.message || "")) {
      throw new Error(`Network request failed (${netErr.message}). Check connection or deployment access.`);
    }
    throw netErr;
  }

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
      try {
        resp = await fetch(path, {
          ...init,
          credentials: "same-origin",
          headers: buildHeaders(retryToken),
        });
      } catch (netErr: any) {
        if (netErr?.name === "TypeError" && /load failed|failed to fetch/i.test(netErr?.message || "")) {
          throw new Error(`Network request failed (${netErr.message}). Check connection or deployment access.`);
        }
        throw netErr;
      }
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

export interface StreamNeonOptions {
  prompt: string;
  agentId: string;
  conversationId?: string | null;
  fileIds?: string[];
  reasoningTier?: number;
  onDelta: (chunk: string) => void;
  onMeta?: (meta: any) => void;
  onDone?: (summary: any) => void;
  onError?: (err: Error) => void;
  signal?: AbortSignal;
}

export async function streamNeon(
  promptOrOptions: string | StreamNeonOptions,
  agentIdArg?: string,
  onDeltaArg?: (chunk: string) => void,
  onMetaArg?: (meta: any) => void,
  fileIdsArg?: string[]
): Promise<void> {
  const opts: StreamNeonOptions =
    typeof promptOrOptions === "object"
      ? promptOrOptions
      : {
          prompt: promptOrOptions,
          agentId: agentIdArg || "AGT-01",
          onDelta: onDeltaArg || (() => {}),
          onMeta: onMetaArg,
          fileIds: fileIdsArg,
        };

  const {
    prompt,
    agentId,
    conversationId,
    fileIds,
    reasoningTier,
    onDelta,
    onMeta,
    onDone,
    onError,
    signal,
  } = opts;

  // 30-second timeout controller combined with caller's signal
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => {
    timeoutController.abort(new Error("NEON streaming request timed out after 30 seconds."));
  }, 30000);

  const abortListener = () =>
    timeoutController.abort(signal?.reason || new Error("Streaming aborted by user."));
  if (signal) {
    if (signal.aborted) {
      clearTimeout(timeoutId);
      throw signal.reason || new Error("Streaming aborted.");
    }
    signal.addEventListener("abort", abortListener);
  }

  try {
    const resp = await fetchWithAutoRefresh(
      "/api/v1/neon/stream",
      {
        method: "POST",
        signal: timeoutController.signal,
        body: JSON.stringify({
          prompt,
          agent_id: agentId,
          conversation_id: conversationId || undefined,
          file_ids: fileIds && fileIds.length > 0 ? fileIds : undefined,
          reasoning_tier: reasoningTier,
          enable_web_research: true,
        }),
      },
      { "Content-Type": "application/json" }
    );
    if (!resp.ok || !resp.body) {
      const errText = await resp.text().catch(() => "");
      let parsedMsg = "";
      try {
        const parsed = JSON.parse(errText);
        parsedMsg = parsed.error?.message || parsed.detail || "";
      } catch {
        // raw text
      }
      if (resp.status === 401) {
        clearSession("session_expired");
        throw new Error(parsedMsg || "Session expired or authentication required. Please sign in.");
      }
      throw new Error(`Stream failed (HTTP ${resp.status}): ${parsedMsg || errText || resp.statusText}`);
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
            if (currentEvent === "done" && onDone) onDone(parsed);
          } catch {
            // ignore malformed keepalives
          }
        }
      }
    }
  } catch (err: any) {
    if (onError) {
      onError(err);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
    if (signal) {
      signal.removeEventListener("abort", abortListener);
    }
  }
}
