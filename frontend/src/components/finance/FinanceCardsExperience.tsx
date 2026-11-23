import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Camera,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Edit3,
  Plus,
  ShieldCheck,
  Star,
  Trash2,
} from "lucide-react";
import { apiFetch, fetchAuthBlobUrl } from "../../lib/api";
import {
  ConfirmationDialog,
  Drawer,
  EmptyState,
  StatusIndicator,
  useToast,
} from "../ui/DesignSystem";

const CARD_BACKGROUNDS: Record<string, string> = {
  "emerald-obsidian": "linear-gradient(135deg, #064e3b 0%, #091318 58%, #042f2e 100%)",
  "midnight-teal": "linear-gradient(135deg, #0f172a 0%, #083344 55%, #020617 100%)",
  "carbon-slate": "linear-gradient(135deg, #18181b 0%, #27272a 55%, #09090b 100%)",
  "aurora-dark": "linear-gradient(135deg, #065f46 0%, #1e1b4b 55%, #090d16 100%)",
};

function connectionTone(status: string): "success" | "info" | "warn" | "neutral" {
  const s = (status || "").toUpperCase();
  if (s === "PROVIDER_LINKED") return "success";
  if (s === "AWAITING_PROVIDER_AUTH") return "warn";
  if (s === "UNSUPPORTED_PROVIDER") return "neutral";
  return "info";
}

export function FinanceCardsExperience({ scope }: { scope?: string }) {
  const { pushToast } = useToast();
  const [cards, setCards] = useState<any[]>([]);
  const [supportedProviders, setSupportedProviders] = useState<string[]>(["paystack", "flutterwave", "stripe"]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [blobUrls, setBlobUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  // Add / Edit Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingCard, setEditingCard] = useState<any | null>(null);
  const [nickname, setNickname] = useState("");
  const [issuer, setIssuer] = useState("");
  const [network, setNetwork] = useState("");
  const [cardType, setCardType] = useState("VIRTUAL");
  const [cardScope, setCardScope] = useState("BUSINESS");
  const [bgStyle, setBgStyle] = useState("emerald-obsidian");
  const [accentColor, setAccentColor] = useState("#10b981");
  const [visualEffect, setVisualEffect] = useState("glass");
  const [providerKey, setProviderKey] = useState("manual");
  const [providerTokenRef, setProviderTokenRef] = useState("");
  const [cropZoom, setCropZoom] = useState(1);
  const [displayOrder, setDisplayOrder] = useState(0);
  const [isPreferred, setIsPreferred] = useState(false);
  const [pendingPhoto, setPendingPhoto] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);

  // Delete confirmation
  const [confirmUnlink, setConfirmUnlink] = useState<any | null>(null);
  // Sanitized image preview & confirmation before saving
  const [sanitizedPreview, setSanitizedPreview] = useState<{
    cardId: string;
    file: File;
    previewDataUrl: string;
    redactionMode: "standard" | "full";
    loading: boolean;
  } | null>(null);
  const touchStartX = useRef<number | null>(null);

  async function loadCards() {
    setLoading(true);
    try {
      const qs = scope ? `?scope=${encodeURIComponent(scope)}` : "";
      const res = await apiFetch<any>(`/api/v1/finance/cards${qs}`);
      const list = res.cards || [];
      setCards(list);
      if (Array.isArray(res.supported_providers)) setSupportedProviders(res.supported_providers);
      setActiveIndex((idx) => (list.length === 0 ? 0 : Math.min(idx, list.length - 1)));
    } catch (e: any) {
      pushToast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCards();
  }, [scope]);

  // Fetch authenticated sanitized card images
  useEffect(() => {
    let active = true;
    const created: string[] = [];
    for (const c of cards) {
      if (c.image_preview_url && !blobUrls[c.card_id]) {
        fetchAuthBlobUrl(c.image_preview_url)
          .then((url) => {
            created.push(url);
            if (active) setBlobUrls((prev) => ({ ...prev, [c.card_id]: url }));
            else URL.revokeObjectURL(url);
          })
          .catch(() => {});
      }
    }
    return () => {
      active = false;
      created.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [cards]);

  const activeCard = useMemo(() => cards[activeIndex] || null, [cards, activeIndex]);

  function openAddDrawer() {
    setEditingCard(null);
    setNickname("");
    setIssuer("");
    setNetwork("");
    setCardType("VIRTUAL");
    setCardScope(scope || "BUSINESS");
    setBgStyle("emerald-obsidian");
    setAccentColor("#10b981");
    setVisualEffect("glass");
    setProviderKey("manual");
    setProviderTokenRef("");
    setCropZoom(1);
    setDisplayOrder(cards.length);
    setIsPreferred(cards.length === 0);
    setPendingPhoto(null);
    setDrawerOpen(true);
  }

  function openEditDrawer(card: any) {
    setEditingCard(card);
    setNickname(card.nickname || "");
    setIssuer(card.issuer || "");
    setNetwork(card.network || "");
    setCardType(card.card_type || "VIRTUAL");
    setCardScope(card.scope || "BUSINESS");
    setBgStyle(card.background_style || "emerald-obsidian");
    setAccentColor(card.accent_color || "#10b981");
    setVisualEffect(card.visual_effect || "glass");
    setProviderKey(card.provider_key || "manual");
    setProviderTokenRef("");
    setCropZoom(Number(card.image_crop?.zoom || 1));
    setDisplayOrder(Number(card.display_order || 0));
    setIsPreferred(Boolean(card.is_preferred));
    setPendingPhoto(null);
    setDrawerOpen(true);
  }

  async function saveCard(e: React.FormEvent) {
    e.preventDefault();
    if (!nickname.trim()) return;
    setSaving(true);
    try {
      let cardId = editingCard?.card_id;
      const payload: any = {
        nickname: nickname.trim(),
        issuer: issuer.trim() || "Custom",
        network,
        card_type: cardType,
        scope: cardScope,
        background_style: bgStyle,
        accent_color: accentColor,
        visual_effect: visualEffect,
        image_crop: { zoom: cropZoom, offsetX: 0, offsetY: 0 },
        display_order: displayOrder,
        is_preferred: isPreferred,
        provider_key: providerKey === "manual" ? null : providerKey,
      };
      if (providerTokenRef.trim()) {
        payload.provider_token_ref = providerTokenRef.trim();
      }

      if (editingCard) {
        await apiFetch(`/api/v1/finance/cards/${cardId}`, { method: "PATCH", body: payload });
      } else {
        const created = await apiFetch<any>("/api/v1/finance/cards", { method: "POST", body: payload });
        cardId = created.card_id;
      }

      if (pendingPhoto && cardId) {
        const fd = new FormData();
        fd.append("file", pendingPhoto);
        await apiFetch(`/api/v1/finance/cards/${cardId}/image`, {
          method: "POST",
          body: fd,
          isFormData: true,
        });
        // Clear cached blob URL so fresh sanitized image loads
        setBlobUrls((prev) => {
          const next = { ...prev };
          delete next[cardId!];
          return next;
        });
      }

      setDrawerOpen(false);
      pushToast(editingCard ? "Card updated safely." : "Card added safely.", "success");
      await loadCards();
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function requestSanitizedPreview(cardId: string, file: File, redactionMode: "standard" | "full" = "standard") {
    try {
      setSanitizedPreview({ cardId, file, previewDataUrl: "", redactionMode, loading: true });
      const fd = new FormData();
      fd.append("file", file);
      fd.append("redaction_mode", redactionMode);
      const res = await apiFetch<any>(`/api/v1/finance/cards/${cardId}/image/preview`, {
        method: "POST",
        body: fd,
        isFormData: true,
      });
      setSanitizedPreview({
        cardId,
        file,
        previewDataUrl: res.preview_data_url || "",
        redactionMode,
        loading: false,
      });
    } catch (err: any) {
      setSanitizedPreview(null);
      pushToast(err.message, "error");
    }
  }

  async function confirmAndSaveSanitizedImage() {
    if (!sanitizedPreview) return;
    const { cardId, file, redactionMode } = sanitizedPreview;
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("redaction_mode", redactionMode);
      await apiFetch(`/api/v1/finance/cards/${cardId}/image`, {
        method: "POST",
        body: fd,
        isFormData: true,
      });
      setBlobUrls((prev) => {
        const next = { ...prev };
        delete next[cardId];
        return next;
      });
      setSanitizedPreview(null);
      pushToast("Sanitized card image verified & saved.", "success");
      await loadCards();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  return (
    <div className="finance-cards-stage" data-testid="finance-cards-experience">
      <div className="row-between" style={{ width: "100%", flexWrap: "wrap", gap: 10 }}>
        <div>
          <div className="eyebrow-mono" style={{ color: "#10b981" }}>ULTRON CARDS // ZERO RAW PAN OR CVV</div>
          <h3 style={{ margin: "2px 0 0", fontSize: 18 }}>Digital Card Vault ({cards.length})</h3>
        </div>
        <button id="finance-add-card-btn" type="button" className="btn btn-sm" style={{ background: "#10b981", color: "#03150e" }} onClick={openAddDrawer}>
          <Plus size={14} /> Add Card
        </button>
      </div>

      {cards.length === 0 ? (
        <EmptyState
          title={loading ? "Loading Cards..." : "No Cards Linked Yet"}
          description="Add a display card or upload a card photograph. Sensitive numbers, CVV, and expiry dates are automatically redacted."
          action={
            <button type="button" className="btn btn-sm" style={{ background: "#10b981", color: "#03150e" }} onClick={openAddDrawer}>
              <Plus size={14} /> Add Your First Card
            </button>
          }
        />
      ) : (
        <>
          {/* Swipeable Floating Card Carousel */}
          <div
            className="finance-card-carousel-row"
            onTouchStart={(e) => {
              touchStartX.current = e.touches[0]?.clientX ?? null;
            }}
            onTouchEnd={(e) => {
              if (touchStartX.current === null) return;
              const dx = (e.changedTouches[0]?.clientX ?? 0) - touchStartX.current;
              if (dx < -40 && activeIndex < cards.length - 1) setActiveIndex((i) => i + 1);
              if (dx > 40 && activeIndex > 0) setActiveIndex((i) => i - 1);
              touchStartX.current = null;
            }}
          >
            {cards.length > 1 && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                aria-label="Previous card"
                disabled={activeIndex === 0}
                onClick={() => setActiveIndex((i) => Math.max(0, i - 1))}
              >
                <ChevronLeft size={16} />
              </button>
            )}

            {activeCard && (
              <div
                className={`finance-floating-card effect-${activeCard.visual_effect || "glass"}`}
                style={{
                  background:
                    activeCard.background_style === "custom-image" && blobUrls[activeCard.card_id]
                      ? "#070a0f"
                      : CARD_BACKGROUNDS[activeCard.background_style] || CARD_BACKGROUNDS["emerald-obsidian"],
                  borderColor: `${activeCard.accent_color || "#10b981"}55`,
                }}
              >
                {activeCard.background_style === "custom-image" && blobUrls[activeCard.card_id] && (
                  <img
                    src={blobUrls[activeCard.card_id]}
                    alt={activeCard.nickname}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      transform: `scale(${activeCard.image_crop?.zoom || 1})`,
                      opacity: 0.9,
                      pointerEvents: "none",
                    }}
                  />
                )}
                <div style={{ position: "relative", zIndex: 1, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div className="mono" style={{ fontSize: 10.5, letterSpacing: "0.08em", opacity: 0.85 }}>
                      {activeCard.issuer || "ULTRON"} · {activeCard.card_type}
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 700, marginTop: 2 }}>{activeCard.nickname}</div>
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    {activeCard.is_preferred && (
                      <span className="pill" style={{ background: "rgba(16,185,129,0.22)", color: "#34d399", fontSize: 10.5 }}>
                        <Star size={10} style={{ marginRight: 3 }} /> Preferred
                      </span>
                    )}
                    {activeCard.network && (
                      <span className="pill mono" style={{ fontSize: 11 }}>{activeCard.network}</span>
                    )}
                  </div>
                </div>

                <div style={{ position: "relative", zIndex: 1, display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                  <div className="mono" style={{ fontSize: 13, letterSpacing: "0.14em", opacity: 0.8 }}>
                    ••••  ••••  ••••  SAFE
                  </div>
                  <span className="pill mono" style={{ fontSize: 10.5 }}>{activeCard.scope}</span>
                </div>
              </div>
            )}

            {cards.length > 1 && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                aria-label="Next card"
                disabled={activeIndex === cards.length - 1}
                onClick={() => setActiveIndex((i) => Math.min(cards.length - 1, i + 1))}
              >
                <ChevronRight size={16} />
              </button>
            )}
          </div>

          {/* Carousel Dots & Card Switcher */}
          {cards.length > 1 && (
            <div className="row" style={{ gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
              {cards.map((c, idx) => (
                <button
                  key={c.card_id}
                  type="button"
                  className={`seg-btn ${idx === activeIndex ? "active" : ""}`}
                  onClick={() => setActiveIndex(idx)}
                >
                  <CreditCard size={11} /> {c.nickname}
                </button>
              ))}
            </div>
          )}

          {/* Dark Charcoal Card Information Panel */}
          {activeCard && (
            <div className="finance-card-info-panel">
              <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
                <div className="row" style={{ gap: 8 }}>
                  <ShieldCheck size={16} style={{ color: "#10b981" }} />
                  <strong>Card Details &amp; Connection Status</strong>
                </div>
                <StatusIndicator label={activeCard.connection_status} tone={connectionTone(activeCard.connection_status)} />
              </div>

              <div className="finance-card-info-grid">
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Card Nickname</div>
                  <strong>{activeCard.nickname}</strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Issuer / Provider</div>
                  <strong>{activeCard.issuer}</strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Card Network</div>
                  <strong>{activeCard.network || "Not specified"}</strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Card Type</div>
                  <strong>{activeCard.card_type}</strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Account Scope</div>
                  <strong>{activeCard.scope}</strong>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Last Sync</div>
                  <strong>{activeCard.last_synced_at ? activeCard.last_synced_at.slice(0, 16).replace("T", " ") : "Display only"}</strong>
                </div>
              </div>

              <div className="muted" style={{ fontSize: 12 }}>
                {activeCard.provider_support_note}
              </div>

              <div className="row" style={{ flexWrap: "wrap", gap: 8, paddingTop: 6, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
                  <Camera size={12} /> Upload Card Photo
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    style={{ display: "none" }}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      e.target.value = "";
                      if (f) requestSanitizedPreview(activeCard.card_id, f, "standard");
                    }}
                  />
                </label>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => openEditDrawer(activeCard)}>
                  <Edit3 size={12} /> Edit Card
                </button>
                {!activeCard.is_preferred && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={async () => {
                      await apiFetch(`/api/v1/finance/cards/${activeCard.card_id}`, {
                        method: "PATCH",
                        body: { is_preferred: true },
                      });
                      pushToast(`'${activeCard.nickname}' set as preferred card.`, "success");
                      await loadCards();
                    }}
                  >
                    <Star size={12} /> Set Preferred
                  </button>
                )}
                <button type="button" className="btn btn-danger btn-sm" onClick={() => setConfirmUnlink(activeCard)}>
                  <Trash2 size={12} /> Unlink
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Add / Edit Card Drawer */}
      <Drawer open={drawerOpen} title={editingCard ? `Edit Card: ${editingCard.nickname}` : "Add Card to ULTRON"} onClose={() => setDrawerOpen(false)}>
        <form onSubmit={saveCard} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="alert-box" style={{ fontSize: 12 }}>
            <strong>PCI &amp; Credential Guard:</strong> Never enter a full card number, CVV, expiry date, or PIN. Uploaded card photos are automatically redacted over the credential zone.
          </div>

          <input className="input" value={nickname} onChange={(e) => setNickname(e.target.value)} placeholder="Card Nickname (e.g., ULTRON Emerald)" required />

          <div className="row" style={{ gap: 8 }}>
            <input className="input" style={{ flex: 1 }} value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="Issuing Bank / Provider" />
            <select className="select" style={{ flex: 1 }} value={network} onChange={(e) => setNetwork(e.target.value)} aria-label="Card Network">
              <option value="">No Network Logo</option>
              <option value="VISA">VISA</option>
              <option value="MASTERCARD">MASTERCARD</option>
              <option value="VERVE">VERVE</option>
              <option value="AMEX">AMEX</option>
              <option value="OTHER">OTHER</option>
            </select>
          </div>

          <div className="row" style={{ gap: 8 }}>
            <select className="select" style={{ flex: 1 }} value={cardType} onChange={(e) => setCardType(e.target.value)} aria-label="Card Type">
              <option value="VIRTUAL">VIRTUAL</option>
              <option value="PHYSICAL">PHYSICAL</option>
              <option value="CORPORATE">CORPORATE</option>
              <option value="DEBIT">DEBIT</option>
              <option value="CREDIT">CREDIT</option>
            </select>
            <select className="select" style={{ flex: 1 }} value={cardScope} onChange={(e) => setCardScope(e.target.value)} aria-label="Card Scope">
              <option value="BUSINESS">BUSINESS</option>
              <option value="PERSONAL">PERSONAL</option>
            </select>
          </div>

          <div className="row" style={{ gap: 8 }}>
            <select className="select" style={{ flex: 1 }} value={bgStyle} onChange={(e) => setBgStyle(e.target.value)} aria-label="Background Style">
              <option value="emerald-obsidian">Emerald Obsidian</option>
              <option value="midnight-teal">Midnight Teal</option>
              <option value="carbon-slate">Carbon Slate</option>
              <option value="aurora-dark">Aurora Dark</option>
              <option value="custom-image">Uploaded Card Photo</option>
            </select>
            <select className="select" style={{ flex: 1 }} value={visualEffect} onChange={(e) => setVisualEffect(e.target.value)} aria-label="Visual Effect">
              <option value="glass">Glass</option>
              <option value="metallic">Metallic</option>
              <option value="matte">Matte</option>
              <option value="holographic">Holographic</option>
            </select>
          </div>

          <div className="row" style={{ gap: 8 }}>
            <label className="muted" style={{ fontSize: 12, flex: 1 }}>
              Accent Color
              <input className="input" type="color" value={accentColor} onChange={(e) => setAccentColor(e.target.value)} style={{ height: 36, padding: 2 }} />
            </label>
            <label className="muted" style={{ fontSize: 12, flex: 1 }}>
              Image Zoom ({cropZoom.toFixed(1)}x)
              <input className="input" type="range" min="1" max="1.6" step="0.1" value={cropZoom} onChange={(e) => setCropZoom(Number(e.target.value))} />
            </label>
            <label className="muted" style={{ fontSize: 12, width: 90 }}>
              Order
              <input className="input" type="number" value={displayOrder} onChange={(e) => setDisplayOrder(Number(e.target.value))} />
            </label>
          </div>

          <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
            <Camera size={13} /> {pendingPhoto ? `Selected: ${pendingPhoto.name}` : "Upload Card Photograph (Auto-Redacted)"}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style={{ display: "none" }}
              onChange={(e) => setPendingPhoto(e.target.files?.[0] || null)}
            />
          </label>

          <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="telemetry-label">OPTIONAL TOKENIZED PROVIDER LINKING</div>
            <select className="select" value={providerKey} onChange={(e) => setProviderKey(e.target.value)} aria-label="Provider">
              <option value="manual">Display Only (No Financial Account Linked)</option>
              {supportedProviders.map((p) => (
                <option key={p} value={p}>{p.toUpperCase()} (Tokenized Reference)</option>
              ))}
            </select>
            {providerKey !== "manual" && (
              <input
                className="input mono"
                value={providerTokenRef}
                onChange={(e) => setProviderTokenRef(e.target.value)}
                placeholder="Provider-issued token ref (e.g., AUTH_tok_... or pm_...)"
              />
            )}
          </div>

          <label className="row" style={{ gap: 8, fontSize: 13 }}>
            <input type="checkbox" checked={isPreferred} onChange={(e) => setIsPreferred(e.target.checked)} />
            Set as preferred display card
          </label>

          <button type="submit" className="btn" disabled={saving} style={{ background: "#10b981", color: "#03150e" }}>
            {saving ? "Saving..." : editingCard ? "Save Card Changes" : "Add Card"}
          </button>
        </form>
      </Drawer>

      {/* Sanitized Card Image Preview & Confirmation Drawer */}
      <Drawer
        open={Boolean(sanitizedPreview)}
        title="Verify Sanitized Card Image"
        onClose={() => setSanitizedPreview(null)}
      >
        {sanitizedPreview && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="alert-box" style={{ fontSize: 12 }}>
              <strong>Confirm Credential Redaction:</strong> Verify that no card numbers, CVV, or expiry dates remain visible before saving. If your card is vertical or has numbers near the top, switch to <strong>Full Card Redaction</strong>.
            </div>
            <div className="row" style={{ gap: 8 }}>
              <button
                type="button"
                className={`seg-btn ${sanitizedPreview.redactionMode === "standard" ? "active" : ""}`}
                onClick={() => requestSanitizedPreview(sanitizedPreview.cardId, sanitizedPreview.file, "standard")}
              >
                Standard Zone
              </button>
              <button
                type="button"
                className={`seg-btn ${sanitizedPreview.redactionMode === "full" ? "active" : ""}`}
                onClick={() => requestSanitizedPreview(sanitizedPreview.cardId, sanitizedPreview.file, "full")}
              >
                Full Card Redaction
              </button>
            </div>
            {sanitizedPreview.loading ? (
              <div className="muted">Sanitizing image in memory (stripping EXIF &amp; blurring credential zone)...</div>
            ) : sanitizedPreview.previewDataUrl ? (
              <img
                src={sanitizedPreview.previewDataUrl}
                alt="Sanitized card preview"
                style={{ width: "100%", borderRadius: 16, border: "1px solid rgba(255,255,255,0.16)" }}
              />
            ) : null}
            <div className="row" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn"
                disabled={sanitizedPreview.loading || !sanitizedPreview.previewDataUrl}
                style={{ background: "#10b981", color: "#03150e", flex: 1 }}
                onClick={confirmAndSaveSanitizedImage}
              >
                Confirm &amp; Save Sanitized Image
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setSanitizedPreview(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </Drawer>

      <ConfirmationDialog
        open={Boolean(confirmUnlink)}
        title="Unlink Card"
        message={`Remove '${confirmUnlink?.nickname}' from your ULTRON Finance Centre?`}
        confirmLabel="Unlink Card"
        onCancel={() => setConfirmUnlink(null)}
        onConfirm={async () => {
          if (confirmUnlink) {
            await apiFetch(`/api/v1/finance/cards/${confirmUnlink.card_id}`, { method: "DELETE" });
            pushToast("Card unlinked.", "success");
            await loadCards();
          }
          setConfirmUnlink(null);
        }}
      />
    </div>
  );
}
