import React, { createContext, useContext, useEffect, useState } from "react";

export type ThemeMode = "dark" | "light";
export type AccentPreset = "electric" | "cyan" | "silver" | "emerald";
export type DensityMode = "comfortable" | "compact";
export type LayoutMode = "auto" | "desktop" | "mobile";

export interface UIPreferences {
  theme: ThemeMode;
  accent: AccentPreset;
  density: DensityMode;
  layoutMode: LayoutMode;
  animationsEnabled: boolean;
  reducedMotion: boolean;
  highContrastFocus: boolean;
  language: string;
  region: string;
  sidebarCollapsed: boolean;
  rightPanelOpen: boolean;
}

const PREF_KEY = "ultron_ui_preferences_v1";

const DEFAULT_PREFS: UIPreferences = {
  theme: "dark",
  accent: "electric",
  density: "comfortable",
  layoutMode: "auto",
  animationsEnabled: true,
  reducedMotion: false,
  highContrastFocus: false,
  language: "en-US",
  region: "Global (UTC)",
  sidebarCollapsed: false,
  rightPanelOpen: false,
};

function loadPreferences(): UIPreferences {
  try {
    const raw = localStorage.getItem(PREF_KEY);
    if (!raw) return DEFAULT_PREFS;
    return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<UIPreferences>) };
  } catch {
    return DEFAULT_PREFS;
  }
}

interface PreferencesContextValue {
  prefs: UIPreferences;
  updatePrefs: (patch: Partial<UIPreferences>) => void;
  resetPrefs: () => void;
}

const PreferencesContext = createContext<PreferencesContextValue>({
  prefs: DEFAULT_PREFS,
  updatePrefs: () => {},
  resetPrefs: () => {},
});

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [prefs, setPrefs] = useState<UIPreferences>(loadPreferences);

  useEffect(() => {
    try {
      localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
    } catch {
      // ignore storage quota errors
    }
    const root = document.documentElement;
    root.setAttribute("data-theme", prefs.theme);
    root.setAttribute("data-accent", prefs.accent);
    root.setAttribute("data-density", prefs.density);
    root.setAttribute("data-reduced-motion", String(prefs.reducedMotion || !prefs.animationsEnabled));
    root.setAttribute("data-high-contrast", String(prefs.highContrastFocus));
  }, [prefs]);

  const updatePrefs = (patch: Partial<UIPreferences>) => {
    setPrefs((prev) => ({ ...prev, ...patch }));
  };

  const resetPrefs = () => setPrefs(DEFAULT_PREFS);

  return (
    <PreferencesContext.Provider value={{ prefs, updatePrefs, resetPrefs }}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function usePreferences(): PreferencesContextValue {
  return useContext(PreferencesContext);
}
