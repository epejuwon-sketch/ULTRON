import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Strips bare `crossorigin` from same-origin /assets/ script and stylesheet tags.
 * On protected Vercel Preview deployments (_vercel_jwt cookie), Safari/WebKit treats
 * `crossorigin` ("anonymous") on module scripts/preloads as credential-less in several
 * paths, triggering HTTP 302 redirects to HTML auth pages and throwing
 * "Importing a module script failed." Keeping same-origin tags without `crossorigin`
 * preserves standard same-origin credentials on every browser.
 */
function stripSameOriginCrossorigin(): Plugin {
  return {
    name: "ultron-strip-same-origin-crossorigin",
    transformIndexHtml(html) {
      return html
        .replace(/<script type="module" crossorigin src="\/assets\//g, '<script type="module" src="/assets/')
        .replace(/<link rel="stylesheet" crossorigin href="\/assets\//g, '<link rel="stylesheet" href="/assets/');
    },
  };
}

export default defineConfig({
  base: "/",
  plugins: [react(), stripSameOriginCrossorigin()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  preview: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // Disable Vite's injected <link rel="modulepreload" crossorigin=""> tags both at
    // initial load and during dynamic import(), so Safari/iOS never sends anonymous
    // credential-less requests against protected Vercel Preview deployments.
    modulePreload: {
      polyfill: false,
      resolveDependencies: () => [],
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react/") || id.includes("node_modules/react-dom/") || id.includes("node_modules/scheduler/")) {
            return "vendor-react";
          }
          if (id.includes("node_modules/lucide-react/")) {
            return "vendor-icons";
          }
          if (
            id.includes("/src/components/OpsViews.tsx") ||
            id.includes("/src/components/SystemViews.tsx") ||
            id.includes("/src/components/CoreViews.tsx") ||
            id.includes("/src/components/CommandCenterView.tsx") ||
            id.includes("/src/components/ArgonOrchestrationView.tsx")
          ) {
            return "ultron-views";
          }
        },
      },
    },
  },
});
