import React from "react";
import { RealisticEarth } from "./RealisticEarth";

interface EarthGlobeProps {
  /** Pixel diameter of the globe canvas (scales cleanly with container via CSS). */
  size?: number | string;
  /** Subtle ambient backdrop mode (slower rotation, non-interactive). */
  ambient?: boolean;
  /** Live system health state reflected subtly in telemetry nodes. */
  status?: "ready" | "degraded" | "loading";
  className?: string;
  interactive?: boolean;
}

export function EarthGlobe({
  size = 380,
  ambient = false,
  status = "ready",
  className = "",
  interactive = true,
}: EarthGlobeProps) {
  return (
    <RealisticEarth
      size={size}
      ambient={ambient}
      interactive={interactive && !ambient}
      status={status}
      className={className}
    />
  );
}
export default EarthGlobe;
