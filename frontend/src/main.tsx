import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { installGlobalModuleRecovery } from "./lib/lazyWithRecovery";
import { PreferencesProvider } from "./lib/preferences";
import { ToastProvider } from "./components/ui/DesignSystem";
import "./styles.css";

installGlobalModuleRecovery();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { updateViaCache: "none" })
      .then((reg) => {
        reg.update().catch(() => undefined);
      })
      .catch(() => {
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
