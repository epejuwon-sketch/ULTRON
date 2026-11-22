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

export async function downloadAuthFile(path: string, filename: string): Promise<void> {
  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(path, { headers });
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
  const token = getStoredToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(path, { headers });
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
  const token = getStoredToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch("/api/v1/neon/stream", {
    method: "POST",
    headers,
    body: JSON.stringify({
      prompt,
      agent_id: agentId,
      file_ids: fileIds && fileIds.length > 0 ? fileIds : undefined,
      enable_web_research: true,
    }),
  });
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
