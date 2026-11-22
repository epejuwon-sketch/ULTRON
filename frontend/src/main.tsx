import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { PreferencesProvider } from "./lib/preferences";
import { ToastProvider } from "./components/ui/DesignSystem";
import "./styles.css";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Service worker registration skipped in unsupported environments
    });
  });
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PreferencesProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </PreferencesProvider>
  </React.StrictMode>
);
