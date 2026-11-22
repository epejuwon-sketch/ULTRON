import React from "react";

interface UltronLogoProps {
  variant?: "full" | "compact" | "mark" | "loader" | "empty";
  size?: number;
  subtitle?: string;
}

/**
 * Unified ULTRON OS 2026 Brand Identity Mark.
 * Precision orbital aperture + monolithic U geometry — consistent across
 * desktop rail, iPhone XR topbar, onboarding, loaders, and empty states.
 */
export function UltronLogo({ variant = "mark", size = 32, subtitle }: UltronLogoProps) {
  const svgMark = (px: number, spinning = false) => (
    <svg
      width={px}
      height={px}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      className={spinning ? "ultron-mark-spin" : undefined}
    >
      <rect width="64" height="64" rx="14" fill="var(--logo-bg, #070B12)" />
      <rect x="1.5" y="1.5" width="61" height="61" rx="12.5" stroke="var(--border-strong)" strokeWidth="1.5" />
      <circle
        cx="32"
        cy="32"
        r="21"
        stroke="var(--accent)"
        strokeOpacity="0.34"
        strokeWidth="1.4"
        strokeDasharray={spinning ? "24 12" : undefined}
      />
      <path
        d="M19 20V33.5C19 40.9558 24.8203 47 32 47C39.1797 47 45 40.9558 45 33.5V20"
        stroke="var(--text)"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        d="M25.5 20V33C25.5 36.866 28.4101 40 32 40C35.5899 40 38.5 36.866 38.5 33V20"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="32" cy="14.5" r="2.3" fill="var(--accent)" />
    </svg>
  );

  if (variant === "mark") {
    return <span className="ultron-logo-mark">{svgMark(size)}</span>;
  }

  if (variant === "loader") {
    return (
      <div className="ultron-loader" role="status" aria-live="polite">
        {svgMark(size || 40, true)}
        {subtitle && <span className="muted mono">{subtitle}</span>}
      </div>
    );
  }

  if (variant === "empty") {
    return (
      <div className="ultron-empty-mark" aria-hidden="true">
        {svgMark(size || 44)}
      </div>
    );
  }

  if (variant === "compact") {
    return (
      <div className="ultron-brand-inline">
        {svgMark(size || 28)}
        <span className="brand-title">ULTRON</span>
      </div>
    );
  }

  return (
    <div className="ultron-brand-inline">
      {svgMark(size || 34)}
      <div style={{ minWidth: 0 }}>
        <div className="brand-title">ULTRON OS 2026</div>
        {subtitle && (
          <div className="muted mono" style={{ fontSize: 10.5, overflow: "hidden", textOverflow: "ellipsis" }}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}
