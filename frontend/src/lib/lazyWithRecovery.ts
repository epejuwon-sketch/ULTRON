import React, { ComponentType, lazy } from "react";

const RECOVERY_STORAGE_KEY = "ultron_module_recovery_ts";
const RECOVERY_COOLDOWN_MS = 20_000;

/**
 * Detects dynamic ES module / Vite chunk loading failures across WebKit (iPhone Safari),
 * Chromium, and Firefox.
 */
export function isModuleLoadError(error: unknown): boolean {
  const msg =
    error instanceof Error
      ? `${error.name}: ${error.message}`
      : typeof error === "string"
      ? error
      : String((error as any)?.message || error || "");
  return /importing a module script failed|failed to fetch dynamically imported module|error loading dynamically imported module|chunkloaderror|loading chunk|unable to preload css|expected a javascript module script/i.test(
    msg
  );
}

/**
 * Purges any stale Cache Storage entries and forces a fresh reload of the current route
 * so iPhone Safari / PWA shells never remain trapped on obsolete index.html chunk hashes.
 */
export async function clearCachesAndReload(targetUrl?: string): Promise<void> {
  try {
    if ("caches" in window) {
      const keys = await window.caches.keys();
      await Promise.all(keys.map((k) => window.caches.delete(k)));
    }
  } catch {
    // Best-effort cache cleanup
  }

  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.update().catch(() => r.unregister().catch(() => false))));
    }
  } catch {
    // Best-effort SW refresh
  }

  const nextUrl = targetUrl || window.location.href;
  window.location.replace(nextUrl);
}

function canAttemptAutoReload(): boolean {
  try {
    const raw = window.sessionStorage.getItem(RECOVERY_STORAGE_KEY);
    if (!raw) return true;
    const last = Number(raw);
    if (!Number.isFinite(last)) return true;
    return Date.now() - last > RECOVERY_COOLDOWN_MS;
  } catch {
    return false;
  }
}

function markAutoReloadAttempted(): void {
  try {
    window.sessionStorage.setItem(RECOVERY_STORAGE_KEY, String(Date.now()));
  } catch {
    // Ignore restricted sessionStorage environments
  }
}

/**
 * Resilient React.lazy wrapper for ULTRON OS module pages.
 * On deployment chunk skew (e.g. "Importing a module script failed."), performs a
 * guarded one-shot cache-clearing reload before surfacing an actionable ErrorBoundary state.
 */
export function lazyWithRecovery<T extends ComponentType<any>>(
  importer: () => Promise<{ default: T }>,
  moduleLabel: string
): React.LazyExoticComponent<T> {
  return lazy(async () => {
    try {
      const mod = await importer();
      if (!mod || !mod.default) {
        throw new Error(`Module '${moduleLabel}' loaded without a default export.`);
      }
      return mod;
    } catch (err) {
      if (isModuleLoadError(err) && canAttemptAutoReload()) {
        markAutoReloadAttempted();
        await clearCachesAndReload();
        // Keep Suspense visible briefly while browser navigates to refreshed bundle
        return new Promise<{ default: T }>(() => {});
      }
      throw err;
    }
  });
}

/**
 * Installs a global handler for Vite's vite:preloadError event to recover gracefully
 * when a newer deployment invalidates previously emitted asset hashes.
 */
export function installGlobalModuleRecovery(): void {
  if (typeof window === "undefined") return;
  window.addEventListener("vite:preloadError", (event) => {
    if (canAttemptAutoReload()) {
      event.preventDefault();
      markAutoReloadAttempted();
      void clearCachesAndReload();
    }
  });
}
