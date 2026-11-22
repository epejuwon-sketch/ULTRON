import React from "react";
import { ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";
import { StatusIndicator, StatusTone } from "./DesignSystem";

export interface ProvenanceInfo {
  source?: string;
  retrieved_at?: string;
  verification_status?: string;
  cache_status?: string;
  execution_id?: string;
  sources?: Array<{
    title?: string;
    url?: string;
    domain?: string;
    credibility?: string;
    retrieved_at?: string;
  }>;
}

function statusTone(status?: string): StatusTone {
  const s = String(status || "").toUpperCase();
  if (s.includes("LIVE_VERIFIED") && !s.includes("FALLBACK")) return "success";
  if (s.includes("FALLBACK") || s.includes("CACHED")) return "info";
  if (s.includes("FAIL") || s.includes("UNAVAILABLE")) return "warn";
  return "neutral";
}

export function ProvenanceBar({ provenance }: { provenance?: ProvenanceInfo | null }) {
  if (!provenance) return null;
  const when = provenance.retrieved_at
    ? new Date(provenance.retrieved_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  return (
    <div
      className="row"
      style={{
        flexWrap: "wrap",
        gap: 6,
        marginTop: 8,
        paddingTop: 8,
        borderTop: "1px solid var(--border-subtle, rgba(255,255,255,0.08))",
        fontSize: 11.5,
      }}
    >
      <StatusIndicator
        label={String(provenance.verification_status || "RECORDED").replace(/_/g, " ")}
        tone={statusTone(provenance.verification_status)}
      />
      {provenance.source && <span className="pill mono">Source: {provenance.source}</span>}
      {provenance.cache_status && <span className="pill mono">Cache: {provenance.cache_status}</span>}
      {when && <span className="muted mono">{when}</span>}
      {provenance.execution_id && <span className="muted mono">ID: {provenance.execution_id}</span>}
    </div>
  );
}

export function SourcesList({
  sources,
}: {
  sources?: Array<{ title?: string; url?: string; domain?: string; snippet?: string; retrieved_at?: string }>;
}) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
      <div className="eyebrow-mono" style={{ display: "flex", alignItems: "center", gap: 5 }}>
        <ShieldCheck size={12} /> VERIFIED SOURCES ({sources.length})
      </div>
      {sources.map((s, idx) => (
        <a
          key={s.url || idx}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="list-item"
          style={{
            textDecoration: "none",
            color: "inherit",
            display: "flex",
            flexDirection: "column",
            gap: 3,
            padding: "8px 10px",
          }}
        >
          <div className="row-between">
            <strong style={{ fontSize: 13 }}>{s.title || s.domain || s.url}</strong>
            <ExternalLink size={12} className="muted" />
          </div>
          {s.snippet && (
            <div className="muted" style={{ fontSize: 12 }}>
              {s.snippet}
            </div>
          )}
          <div className="muted mono" style={{ fontSize: 11 }}>
            {s.domain || s.url}
            {s.retrieved_at ? ` · Retrieved ${new Date(s.retrieved_at).toLocaleString()}` : ""}
          </div>
        </a>
      ))}
    </div>
  );
}

/**
 * Collapsible technical diagnostics drawer for authorized debugging.
 * Keeps raw JSON/API payloads strictly hidden from default user-facing interfaces.
 */
export function TechnicalDiagnostics({
  title = "Technical Diagnostics (Authorized Debugging)",
  data,
}: {
  title?: string;
  data: any;
}) {
  if (data === null || data === undefined) return null;
  return (
    <details
      style={{
        marginTop: 10,
        border: "1px solid var(--border-subtle, rgba(255,255,255,0.09))",
        borderRadius: 10,
        padding: "8px 12px",
        background: "rgba(255,255,255,0.02)",
      }}
    >
      <summary
        className="muted mono"
        style={{
          cursor: "pointer",
          fontSize: 11.5,
          display: "flex",
          alignItems: "center",
          gap: 6,
          userSelect: "none",
        }}
      >
        <ChevronRight size={13} /> {title}
      </summary>
      <pre className="code-block" style={{ marginTop: 8, maxHeight: 320, overflow: "auto" }}>
        {typeof data === "string" ? data : JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

function formatReadableValue(val: any): string {
  if (val === null || val === undefined || val === "") return "Unavailable";
  if (typeof val === "boolean") return val ? "Yes" : "No";
  if (typeof val === "number") return String(val);
  if (typeof val === "string") return val;
  if (Array.isArray(val)) {
    if (val.length === 0) return "None";
    if (val.every((v) => typeof v === "string" || typeof v === "number")) {
      return val.slice(0, 6).join(", ") + (val.length > 6 ? ` (+${val.length - 6} more)` : "");
    }
    return `${val.length} item${val.length === 1 ? "" : "s"}`;
  }
  if (typeof val === "object") {
    const keys = Object.keys(val);
    if (keys.length === 0) return "None";
    if ("status" in val) return String(val.status);
    if ("healthy" in val) return val.healthy ? "Healthy" : "Degraded";
    if ("detail" in val && typeof val.detail === "string") return val.detail;
    return `${keys.length} fields recorded`;
  }
  return String(val);
}

/**
 * Converts backend response objects into clean, human-readable summary rows
 * while tucking raw payload details inside TechnicalDiagnostics.
 */
export function ReadableSummary({
  title,
  data,
  diagnosticsTitle,
}: {
  title?: string;
  data: any;
  diagnosticsTitle?: string;
}) {
  if (!data) return null;

  if (typeof data === "string") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {title && <strong>{title}</strong>}
        <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{data}</div>
      </div>
    );
  }

  const narrative =
    typeof data.output === "string"
      ? data.output
      : typeof data.summary === "string"
      ? data.summary
      : typeof data.analysis === "string"
      ? data.analysis
      : typeof data.detail === "string"
      ? data.detail
      : typeof data.message === "string"
      ? data.message
      : null;

  const entries =
    typeof data === "object" && !Array.isArray(data)
      ? Object.entries(data).filter(
          ([k]) =>
            !["output", "summary", "analysis", "raw_text", "verified_sources", "provenance", "extracted_text"].includes(
              k
            )
        )
      : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {title && <div className="eyebrow-mono">{title}</div>}
      {narrative && <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{narrative}</div>}
      {entries.length > 0 && (
        <div className="grid-2" style={{ gap: 8 }}>
          {entries.slice(0, 8).map(([key, value]) => (
            <div key={key} className="list-item" style={{ padding: "8px 10px" }}>
              <div className="muted mono" style={{ fontSize: 11, textTransform: "uppercase" }}>
                {key.replace(/_/g, " ")}
              </div>
              <div style={{ fontSize: 13, marginTop: 2 }}>{formatReadableValue(value)}</div>
            </div>
          ))}
        </div>
      )}
      {Array.isArray(data.verified_sources) && data.verified_sources.length > 0 && (
        <SourcesList sources={data.verified_sources} />
      )}
      {data.provenance && <ProvenanceBar provenance={data.provenance} />}
      <TechnicalDiagnostics title={diagnosticsTitle || "Technical Diagnostics (Authorized Debugging)"} data={data} />
    </div>
  );
}
