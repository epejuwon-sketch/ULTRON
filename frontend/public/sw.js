/* ULTRON OS 2026 Service Worker v3 (Grayscale Rebuild)
 * Security & Reliability Rules:
 * 1. NEVER cache /index.html or content-hashed /assets/*.js|css chunks (prevents chunk-skew on deploys).
 * 2. NEVER intercept /assets/, .js, .mjs, .css, /api/, /ws/, or /health requests.
 * 3. NEVER serve text/html (/index.html) as a fallback for JavaScript or CSS requests.
 * 4. Purge obsolete caches (including v1 and v2) immediately on activation.
 */
const CACHE_NAME = "ultron-shell-2026-v3";
const STATIC_META_ASSETS = ["/manifest.webmanifest", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_META_ASSETS))
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // Only consider same-origin requests for static icon/manifest metadata.
  if (url.origin !== self.location.origin) return;

  // NEVER intercept APIs, WebSockets, health probes, module scripts, stylesheets, or HTML navigations.
  // Passing them straight to the browser guarantees fresh index.html and valid JS MIME types on every deploy.
  if (!STATIC_META_ASSETS.includes(url.pathname)) {
    return;
  }

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => undefined);
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
