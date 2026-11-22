import { useEffect, useState } from "react";

export type DeviceClass = "mobile" | "tablet" | "desktop";

export interface DeviceProfile {
  width: number;
  height: number;
  deviceClass: DeviceClass;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isTouch: boolean;
  isStandalonePWA: boolean;
  isIPhoneXRViewport: boolean;
  prefersReducedMotion: boolean;
}

function readDeviceProfile(): DeviceProfile {
  const width = typeof window !== "undefined" ? window.innerWidth : 1440;
  const height = typeof window !== "undefined" ? window.innerHeight : 900;
  const deviceClass: DeviceClass = width < 768 ? "mobile" : width < 1280 ? "tablet" : "desktop";
  const isTouch =
    typeof window !== "undefined" &&
    ("ontouchstart" in window || navigator.maxTouchPoints > 0 || window.matchMedia?.("(pointer: coarse)")?.matches);
  const isStandalonePWA =
    typeof window !== "undefined" &&
    (window.matchMedia?.("(display-mode: standalone)")?.matches || (window.navigator as any)?.standalone === true);
  const prefersReducedMotion =
    typeof window !== "undefined" &&
    Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches);

  return {
    width,
    height,
    deviceClass,
    isMobile: deviceClass === "mobile",
    isTablet: deviceClass === "tablet",
    isDesktop: deviceClass === "desktop",
    isTouch: Boolean(isTouch),
    isStandalonePWA: Boolean(isStandalonePWA),
    isIPhoneXRViewport: width >= 370 && width <= 430 && height >= 800 && height <= 935,
    prefersReducedMotion,
  };
}

/**
 * Automatic device & viewport capability detection hook.
 * Adapts presentation smoothly across iPhone XR (414x896), compact mobile (375x812),
 * tablets (768-1279), laptops (1280x800), desktops (1440x900), and large monitors (1920x1080+).
 */
export function useDeviceProfile(layoutOverride: "auto" | "desktop" | "mobile" = "auto"): DeviceProfile {
  const [profile, setProfile] = useState<DeviceProfile>(() => readDeviceProfile());

  useEffect(() => {
    const update = () => setProfile(readDeviceProfile());
    window.addEventListener("resize", update, { passive: true });
    window.addEventListener("orientationchange", update, { passive: true });
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    mq?.addEventListener?.("change", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
      mq?.removeEventListener?.("change", update);
    };
  }, []);

  if (layoutOverride === "mobile") {
    return { ...profile, deviceClass: "mobile", isMobile: true, isTablet: false, isDesktop: false };
  }
  if (layoutOverride === "desktop") {
    return { ...profile, deviceClass: "desktop", isMobile: false, isTablet: false, isDesktop: true };
  }
  return profile;
}
