import React from "react";
import { HonestConnectionStatus, IntegrationCatalogEntry } from "../../catalog/integrationsCatalog";
import { StatusIndicator, StatusTone } from "../ui/DesignSystem";
import { IntegrationLogo } from "./IntegrationLogo";

function statusTone(status: HonestConnectionStatus): StatusTone {
  switch (status) {
    case "Connected":
      return "success";
    case "Configuration required":
      return "warn";
    case "Authentication expired":
    case "Error":
      return "danger";
    case "Coming soon":
      return "neutral";
    default:
      return "info";
  }
}

export function IntegrationCard({
  entry,
  status,
  onSelect,
}: {
  entry: IntegrationCatalogEntry;
  status: HonestConnectionStatus;
  onSelect: (entry: IntegrationCatalogEntry) => void;
}) {
  const actionLabel =
    status === "Connected"
      ? "Manage"
      : status === "Coming soon"
      ? "Details"
      : status === "Authentication expired"
      ? "Reconnect"
      : "Configure";

  return (
    <div id={`integration-card-${entry.id}`} className="integration-card">
      <div className="row-between">
        <div className="row" style={{ gap: 10 }}>
          <IntegrationLogo id={entry.id} size={32} />
          <div>
            <div className="integration-card-name">{entry.name}</div>
            <div className="muted" style={{ fontSize: 11.5 }}>{entry.category}</div>
          </div>
        </div>
        <StatusIndicator label={status} tone={statusTone(status)} />
      </div>

      <p className="integration-card-desc">{entry.shortDescription}</p>

      <div className="row-between" style={{ marginTop: "auto", paddingTop: 6 }}>
        <span className="muted mono" style={{ fontSize: 10.5 }}>
          {entry.authFlow === "OAUTH2"
            ? "OAUTH 2.0 + PKCE"
            : entry.authFlow === "API_KEY"
            ? "ENCRYPTED API KEY"
            : entry.authFlow === "SERVER_ENV"
            ? "SERVER ENV"
            : "ROADMAP"}
        </span>
        <button
          id={`integration-action-${entry.id}`}
          type="button"
          className={`btn btn-sm ${status === "Connected" ? "btn-secondary" : ""}`}
          onClick={() => onSelect(entry)}
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}
