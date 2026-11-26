import { FormEvent, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, KeyRound, ShieldCheck } from "lucide-react";
import type { IntegrationCatalogEntry } from "../../catalog/integrationsCatalog";
import { apiFetch, getStoredToken, getStoredUser } from "../../lib/api";
import { useToast } from "../ui/DesignSystem";

interface OAuthAppStatus {
  family: string;
  configured: boolean;
  source: "env" | "vault" | "none";
  client_id_masked?: string | null;
  redirect_uri?: string | null;
  requirements?: {
    authorized_redirect_path?: string;
    required_env_vars?: string[];
    required_google_apis?: string[];
    applies_to_providers?: string[];
  };
}

interface AdminOAuthSetupPanelProps {
  entry: IntegrationCatalogEntry;
  oauthReady: boolean;
  busy?: boolean;
  onConfigured: () => Promise<void> | void;
}

export function AdminOAuthSetupPanel({
  entry,
  oauthReady,
  busy = false,
  onConfigured,
}: AdminOAuthSetupPanelProps) {
  const { pushToast } = useToast();
  const family = entry.backendProviderKey === "github" ? "github" : "google";
  const expectedRedirectUri =
    typeof window !== "undefined" ? `${window.location.origin}/oauth/callback` : "/oauth/callback";

  const [isAdmin, setIsAdmin] = useState<boolean>(() => {
    const role = (getStoredUser()?.role || "").toUpperCase();
    return role === "OWNER" || role === "ADMIN";
  });
  const [appStatus, setAppStatus] = useState<OAuthAppStatus | null>(null);
  const [showUpdateForm, setShowUpdateForm] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function loadStatus() {
    try {
      const res = await apiFetch<OAuthAppStatus>(`/api/v1/integrations/oauth/admin/${family}/status`);
      setAppStatus(res);
    } catch {
      // Keep fallback state if status endpoint fails
    }
  }

  useEffect(() => {
    setFormError("");
    setShowUpdateForm(false);
    loadStatus();
    if (!getStoredUser()?.role && getStoredToken()) {
      apiFetch<any>("/api/v1/auth/me")
        .then((me) => {
          const role = (me?.role || "").toUpperCase();
          setIsAdmin(role === "OWNER" || role === "ADMIN");
        })
        .catch(() => {});
    }
  }, [family, entry.id]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    const cid = clientId.trim();
    const csec = clientSecret.trim();
    if (cid.length < 8 || csec.length < 8 || /\s/.test(cid) || /\s/.test(csec)) {
      const msg =
        family === "google"
          ? "Both GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are required (minimum 8 characters, no whitespace)."
          : "Valid OAuth Client ID and Client Secret are required (minimum 8 characters, no whitespace).";
      setFormError(msg);
      pushToast(msg, "error");
      return;
    }

    setSaving(true);
    try {
      await apiFetch(`/api/v1/integrations/oauth/admin/${family}/configure`, {
        method: "POST",
        body: {
          client_id: cid,
          client_secret: csec,
          redirect_uri: expectedRedirectUri,
        },
      });
      setClientId("");
      setClientSecret("");
      setShowUpdateForm(false);
      pushToast("Administrator OAuth credentials encrypted and saved in VAULT.", "success");
      await loadStatus();
      await onConfigured();
    } catch (err: any) {
      const msg = err?.message || "Failed to save administrator OAuth credentials.";
      setFormError(msg);
      pushToast(msg, "error");
    } finally {
      setSaving(false);
    }
  }

  const effectiveConfigured = Boolean(oauthReady || appStatus?.configured);
  const redirectMismatch =
    Boolean(appStatus?.redirect_uri) &&
    appStatus?.redirect_uri !== expectedRedirectUri;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {!effectiveConfigured ? (
        <div className="muted" style={{ fontSize: 12 }}>
          {entry.name} setup is not yet available. Administrator configuration is required.
        </div>
      ) : (
        <div
          className="row"
          style={{
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 6,
            fontSize: 12,
          }}
        >
          <span style={{ color: "#34d399", display: "inline-flex", alignItems: "center", gap: 4 }}>
            <CheckCircle2 size={13} />
            OAuth App Ready ({appStatus?.source === "env" ? "Server Env" : "VAULT"}
            {appStatus?.client_id_masked ? ` · ${appStatus.client_id_masked}` : ""})
          </span>
          {isAdmin && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowUpdateForm((v) => !v)}
              disabled={busy || saving}
            >
              <KeyRound size={12} /> {showUpdateForm ? "Cancel" : "Update OAuth App"}
            </button>
          )}
        </div>
      )}

      {redirectMismatch && (
        <div style={{ color: "#f59e0b", fontSize: 12 }}>
          <AlertTriangle size={12} style={{ verticalAlign: "middle", marginRight: 4 }} />
          Saved Redirect URI ({appStatus?.redirect_uri}) differs from current origin ({expectedRedirectUri}).
          Update OAuth App below if using this preview/origin.
        </div>
      )}

      {(!effectiveConfigured || showUpdateForm) && (
        <>
          {isAdmin ? (
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 4 }}>
              <div className="telemetry-label">ADMINISTRATOR OAUTH SETUP (VAULT)</div>
              <input
                className="input"
                placeholder={family === "google" ? "GOOGLE_OAUTH_CLIENT_ID" : "GITHUB_OAUTH_CLIENT_ID"}
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                autoComplete="off"
                required
              />
              <input
                className="input"
                type="password"
                placeholder={
                  family === "google"
                    ? "GOOGLE_OAUTH_CLIENT_SECRET (encrypted in VAULT)"
                    : "GITHUB_OAUTH_CLIENT_SECRET (encrypted in VAULT)"
                }
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                autoComplete="new-password"
                required
              />
              <div className="muted mono" style={{ fontSize: 11, wordBreak: "break-all" }}>
                Authorized Redirect URI: {expectedRedirectUri}
              </div>
              {family === "google" && (
                <div className="muted" style={{ fontSize: 11, lineHeight: 1.45 }}>
                  Google Cloud Requirements: Create a Web Application OAuth 2.0 Client in Google Cloud Console,
                  register the Authorized Redirect URI above, configure the OAuth Consent Screen, and enable the
                  required Google Workspace APIs (Drive, Gmail, Calendar, Docs, Sheets, Slides, Cloud). Saving once
                  in VAULT enables all 7 Google Workspace integrations.
                </div>
              )}
              {formError && (
                <div style={{ color: "#f87171", fontSize: 12 }}>
                  <AlertTriangle size={12} style={{ verticalAlign: "middle", marginRight: 4 }} />
                  {formError}
                </div>
              )}
              <button type="submit" className="btn btn-secondary btn-sm" disabled={busy || saving}>
                <ShieldCheck size={12} /> {saving ? "Encrypting in VAULT..." : "Save OAuth App in VAULT"}
              </button>
            </form>
          ) : (
            <div className="muted" style={{ fontSize: 12 }}>
              Only workspace OWNER or ADMIN administrators can configure OAuth application credentials in VAULT.
            </div>
          )}
        </>
      )}
    </div>
  );
}
