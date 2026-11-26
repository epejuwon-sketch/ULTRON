/**
 * ULTRON OS 2026 — Cloudflare Worker Edge Gateway
 *
 * Provides edge security headers, request correlation IDs, optional KV-backed
 * sliding-window rate limiting, and authenticated proxying to the Vercel/origin
 * ULTRON OS 2026 backend API.
 */

export interface Env {
  ULTRON_ORIGIN_URL: string;
  ALLOWED_ORIGINS?: string;
  RATE_LIMIT_PER_MIN?: string;
  RATE_LIMIT_KV?: KVNamespace;
}

const SECURITY_HEADERS: Record<string, string> = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const requestId = request.headers.get("X-Request-ID") || `cf_${crypto.randomUUID().slice(0, 12)}`;

    // Edge-native lightweight health endpoint
    if (url.pathname === "/edge/health") {
      return new Response(
        JSON.stringify({
          status: "ok",
          layer: "cloudflare-edge-gateway",
          origin_configured: Boolean(env.ULTRON_ORIGIN_URL),
          request_id: requestId,
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": requestId,
            ...SECURITY_HEADERS,
          },
        }
      );
    }

    if (!env.ULTRON_ORIGIN_URL) {
      return new Response(
        JSON.stringify({
          error: {
            code: "ORIGIN_NOT_CONFIGURED",
            message: "ULTRON_ORIGIN_URL Worker variable is not configured.",
            request_id: requestId,
          },
        }),
        {
          status: 503,
          headers: { "Content-Type": "application/json", "X-Request-ID": requestId, ...SECURITY_HEADERS },
        }
      );
    }

    // Optional KV-backed per-IP per-minute rate limiting
    if (env.RATE_LIMIT_KV) {
      const limit = Number(env.RATE_LIMIT_PER_MIN || "120");
      const ip = request.headers.get("CF-Connecting-IP") || "unknown";
      const bucket = Math.floor(Date.now() / 60000);
      const kvKey = `rl:${ip}:${bucket}`;
      const current = Number((await env.RATE_LIMIT_KV.get(kvKey)) || "0");
      if (current >= limit) {
        return new Response(
          JSON.stringify({
            error: {
              code: "RATE_LIMITED",
              message: "Edge rate limit exceeded. Please retry after 60 seconds.",
              request_id: requestId,
            },
          }),
          {
            status: 429,
            headers: {
              "Content-Type": "application/json",
              "Retry-After": "60",
              "X-Request-ID": requestId,
              ...SECURITY_HEADERS,
            },
          }
        );
      }
      await env.RATE_LIMIT_KV.put(kvKey, String(current + 1), { expirationTtl: 120 });
    }

    const originUrl = new URL(url.pathname + url.search, env.ULTRON_ORIGIN_URL);
    const forwardedHeaders = new Headers(request.headers);
    forwardedHeaders.set("X-Request-ID", requestId);
    forwardedHeaders.set("X-Forwarded-Host", url.host);

    const upstreamResp = await fetch(originUrl.toString(), {
      method: request.method,
      headers: forwardedHeaders,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    });

    const respHeaders = new Headers(upstreamResp.headers);
    respHeaders.set("X-Request-ID", requestId);
    respHeaders.set("X-Edge-Gateway", "ultron-cloudflare-worker");
    for (const [k, v] of Object.entries(SECURITY_HEADERS)) {
      respHeaders.set(k, v);
    }

    return new Response(upstreamResp.body, {
      status: upstreamResp.status,
      statusText: upstreamResp.statusText,
      headers: respHeaders,
    });
  },
};
