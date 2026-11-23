import React, { useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Globe,
  Image as ImageIcon,
  ImageOff,
  MapPin,
  ShieldCheck,
  Tag,
} from "lucide-react";
import { StatusIndicator } from "./DesignSystem";

export interface ProductImageItem {
  image_url: string;
  full_image_url?: string;
  title?: string;
  source_page_url?: string;
  source_domain?: string;
  image_type?: string;
  image_type_label?: string;
  attribution?: string;
}

export interface ProductListingItem {
  title: string;
  url: string;
  domain: string;
  seller_or_publisher?: string;
  category?: string;
  category_label?: string;
  credibility?: string;
  image_url?: string | null;
  image_type_label?: string | null;
  advertised_price?: string | null;
  currency?: string | null;
  price_type?: string;
  price_type_label?: string;
  is_completed_sale?: boolean;
  country?: string;
  region?: string;
  condition?: string | null;
  mileage?: string | null;
  all_extracted_prices?: string[];
  summary_excerpt?: string;
  page_fetched?: boolean;
  last_checked_at?: string;
}

export interface ProductPriceEvidenceItem {
  formatted_price: string;
  amount: number;
  currency: string;
  country: string;
  region: string;
  price_type: string;
  price_type_label: string;
  is_completed_sale: boolean;
  condition?: string;
  mileage?: string | null;
  context_excerpt?: string;
  source_title?: string;
  source_url?: string;
  source_domain?: string;
  retrieved_at?: string;
}

export interface ProductIntelligenceData {
  detected?: boolean;
  product?: {
    product_name?: string;
    manufacturer?: string;
    model?: string;
    variant?: string;
    year?: string;
    product_category?: string;
  };
  specifications?: Array<{ label: string; value: string }>;
  images?: ProductImageItem[];
  image_availability_status?: string;
  listings?: ProductListingItem[];
  price_evidence?: ProductPriceEvidenceItem[];
  pricing_summary?: {
    original_msrp?: ProductPriceEvidenceItem[];
    active_asking_prices?: ProductPriceEvidenceItem[];
    confirmed_completed_sales?: ProductPriceEvidenceItem[];
    regions_covered?: string[];
    currencies_detected?: string[];
    nigeria_market_evidence?: {
      checked?: boolean;
      verified_local_listings_found?: boolean;
      candidate_sources_inspected?: number;
      note?: string;
    };
  };
  retrieved_at?: string;
}

function priceTypeTone(priceType?: string): "success" | "info" | "warn" | "neutral" {
  const t = String(priceType || "").toUpperCase();
  if (t === "COMPLETED_SALE") return "success";
  if (t === "ORIGINAL_MSRP") return "info";
  if (t.includes("UNVERIFIED")) return "warn";
  return "neutral";
}

function formatShortDate(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function ProductDiscoveryShowcase({
  data,
}: {
  data?: ProductIntelligenceData | null;
}) {
  const [activeImageIdx, setActiveImageIdx] = useState(0);
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});
  const [loadedImages, setLoadedImages] = useState<Record<string, boolean>>({});
  const [activeFilter, setActiveFilter] = useState<"ALL" | "ASKING" | "SOLD" | "MSRP">("ALL");

  if (!data || !data.detected || !data.product) return null;

  const product = data.product;
  const specs = data.specifications || [];
  const allImages = (data.images || []).filter(
    (img) => img.image_url && !failedImages[img.image_url]
  );
  const safeIdx = allImages.length > 0 ? Math.min(activeImageIdx, allImages.length - 1) : 0;
  const currentImg = allImages[safeIdx];

  const listings = data.listings || [];
  const filteredListings = listings.filter((item) => {
    if (activeFilter === "ALL") return true;
    if (activeFilter === "SOLD") return Boolean(item.is_completed_sale);
    if (activeFilter === "MSRP") return item.price_type === "ORIGINAL_MSRP" || item.category === "manufacturer_msrp";
    return !item.is_completed_sale;
  });

  const summary = data.pricing_summary || {};
  const msrpList = summary.original_msrp || [];
  const askingList = summary.active_asking_prices || [];
  const soldList = summary.confirmed_completed_sales || [];
  const ngEvidence = summary.nigeria_market_evidence;

  return (
    <div
      className="card"
      data-testid="product-discovery-showcase"
      style={{
        marginTop: 10,
        marginBottom: 10,
        border: "1px solid rgba(56, 189, 248, 0.25)",
        background: "linear-gradient(180deg, rgba(15, 23, 42, 0.85) 0%, rgba(9, 13, 24, 0.92) 100%)",
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      {/* 1. PRODUCT IDENTITY HEADER */}
      <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
        <div>
          <div className="eyebrow-mono" style={{ color: "var(--accent, #38bdf8)" }}>
            VISUAL PRODUCT DISCOVERY // {product.product_category?.toUpperCase() || "MARKET INTELLIGENCE"}
          </div>
          <h3 style={{ margin: "3px 0 0", fontSize: 17, fontWeight: 700 }}>
            {product.product_name}
          </h3>
          <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {product.manufacturer && (
              <span className="pill mono">Manufacturer: {product.manufacturer}</span>
            )}
            {product.model && <span className="pill mono">Model: {product.model}</span>}
            {product.variant && (
              <span className="pill pill-cyan mono">Variant: {product.variant}</span>
            )}
            {product.year && <span className="pill mono">Year: {product.year}</span>}
          </div>
        </div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          <StatusIndicator
            label={allImages.length > 0 ? `${allImages.length} VERIFIED PHOTO${allImages.length === 1 ? "" : "S"}` : "IMAGE UNAVAILABLE"}
            tone={allImages.length > 0 ? "success" : "neutral"}
          />
          <StatusIndicator
            label={`${listings.length} LIVE SOURCE${listings.length === 1 ? "" : "S"}`}
            tone="info"
          />
        </div>
      </div>

      {/* 2. PRODUCT IMAGE GALLERY + SPECIFICATIONS GRID */}
      <div className="grid-2" style={{ alignItems: "stretch", gap: 14 }}>
        {/* Image Gallery with Official vs Listing Attribution & Honest Fallback State */}
        <div
          style={{
            border: "1px solid var(--border-subtle, rgba(255,255,255,0.09))",
            borderRadius: 12,
            overflow: "hidden",
            background: "rgba(0,0,0,0.35)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          {currentImg ? (
            <>
              <div style={{ position: "relative", minHeight: 210, maxHeight: 290, display: "flex", alignItems: "center", justifyContent: "center", background: "#050811" }}>
                {!loadedImages[currentImg.image_url] && (
                  <div className="muted mono" style={{ position: "absolute", fontSize: 11.5 }}>
                    Loading verified product photograph...
                  </div>
                )}
                <img
                  src={currentImg.image_url}
                  alt={currentImg.title || product.product_name || "Product photograph"}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  onLoad={() =>
                    setLoadedImages((prev) => ({ ...prev, [currentImg.image_url]: true }))
                  }
                  onError={() =>
                    setFailedImages((prev) => ({ ...prev, [currentImg.image_url]: true }))
                  }
                  style={{
                    width: "100%",
                    maxHeight: 280,
                    objectFit: "cover",
                    display: "block",
                    opacity: loadedImages[currentImg.image_url] ? 1 : 0.15,
                    transition: "opacity 0.2s ease",
                  }}
                />
                {/* Distinction badge: Official Manufacturer vs Listing / Auction / Commons */}
                <div
                  style={{
                    position: "absolute",
                    top: 8,
                    left: 8,
                    background: "rgba(9, 13, 24, 0.86)",
                    backdropFilter: "blur(6px)",
                    padding: "4px 8px",
                    borderRadius: 6,
                    border: "1px solid rgba(255,255,255,0.14)",
                    fontSize: 10.5,
                  }}
                  className="mono"
                >
                  <ImageIcon size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />
                  {currentImg.image_type_label || "Verified Source Photograph"}
                </div>
                {allImages.length > 1 && (
                  <div
                    style={{
                      position: "absolute",
                      bottom: 8,
                      right: 8,
                      display: "flex",
                      gap: 5,
                    }}
                  >
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      aria-label="Previous product photo"
                      onClick={() =>
                        setActiveImageIdx((prev) => (prev - 1 + allImages.length) % allImages.length)
                      }
                    >
                      <ChevronLeft size={13} />
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      aria-label="Next product photo"
                      onClick={() => setActiveImageIdx((prev) => (prev + 1) % allImages.length)}
                    >
                      <ChevronRight size={13} />
                    </button>
                  </div>
                )}
              </div>

              <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                <div className="row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>
                    {(currentImg.title || product.product_name || "").slice(0, 75)}
                  </span>
                  {currentImg.source_page_url && (
                    <a
                      href={currentImg.source_page_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="pill mono"
                      style={{ textDecoration: "none", fontSize: 10.5, display: "inline-flex", alignItems: "center", gap: 4 }}
                    >
                      Photo Source: {currentImg.source_domain || "Open"} <ExternalLink size={10} />
                    </a>
                  )}
                </div>

                {/* Thumbnail strip */}
                {allImages.length > 1 && (
                  <div
                    className="row"
                    style={{
                      gap: 6,
                      overflowX: "auto",
                      paddingBottom: 2,
                    }}
                  >
                    {allImages.map((img, i) => (
                      <button
                        key={img.image_url}
                        type="button"
                        onClick={() => setActiveImageIdx(i)}
                        aria-label={`View photo ${i + 1}`}
                        style={{
                          border:
                            i === safeIdx
                              ? "2px solid var(--accent, #38bdf8)"
                              : "1px solid rgba(255,255,255,0.14)",
                          borderRadius: 6,
                          padding: 0,
                          width: 48,
                          height: 36,
                          overflow: "hidden",
                          cursor: "pointer",
                          background: "#050811",
                          flexShrink: 0,
                        }}
                      >
                        <img
                          src={img.image_url}
                          alt={img.title || `Thumbnail ${i + 1}`}
                          loading="lazy"
                          referrerPolicy="no-referrer"
                          onError={() =>
                            setFailedImages((prev) => ({ ...prev, [img.image_url]: true }))
                          }
                          style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                        />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div
              style={{
                minHeight: 200,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: 20,
                textAlign: "center",
                gap: 8,
              }}
            >
              <ImageOff size={28} className="muted" />
              <strong style={{ fontSize: 13 }}>Verified Photograph Unavailable</strong>
              <span className="muted" style={{ fontSize: 12, maxWidth: 290 }}>
                No verified public product photograph was returned by the live sources. ULTRON never generates synthetic placeholder photos for real-world products or listings.
              </span>
            </div>
          )}
        </div>

        {/* Specifications & Market Valuation Separation Panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Pricing Evidence Matrix: Original MSRP vs Active Asking vs Confirmed Completed Sales */}
          <div
            style={{
              border: "1px solid var(--border-subtle, rgba(255,255,255,0.09))",
              borderRadius: 12,
              padding: "10px 12px",
              background: "rgba(255,255,255,0.02)",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div className="eyebrow-mono" style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <Tag size={12} /> VERIFIED PRICING &amp; TRANSACTION EVIDENCE
            </div>
            <div className="grid-3" style={{ gap: 8 }}>
              <div className="list-item" style={{ padding: "8px 10px" }}>
                <div className="muted mono" style={{ fontSize: 10.5 }}>ORIGINAL MSRP</div>
                <strong style={{ fontSize: 14, display: "block", marginTop: 2 }}>
                  {msrpList[0]?.formatted_price || "See Sources"}
                </strong>
                <span className="muted" style={{ fontSize: 11 }}>
                  {msrpList[0] ? `${msrpList[0].currency} · Factory Launch` : "Manufacturer baseline"}
                </span>
              </div>
              <div className="list-item" style={{ padding: "8px 10px" }}>
                <div className="muted mono" style={{ fontSize: 10.5 }}>ACTIVE ASKING PRICES</div>
                <strong style={{ fontSize: 14, display: "block", marginTop: 2, color: "var(--accent, #38bdf8)" }}>
                  {askingList[0]?.formatted_price || "See Listings"}
                </strong>
                <span className="muted" style={{ fontSize: 11 }}>
                  {askingList[0]
                    ? `${askingList[0].country} (Asking, not sold)`
                    : "Dealer / seller quotes"}
                </span>
              </div>
              <div className="list-item" style={{ padding: "8px 10px" }}>
                <div className="muted mono" style={{ fontSize: 10.5 }}>CONFIRMED COMPLETED SALES</div>
                <strong style={{ fontSize: 14, display: "block", marginTop: 2, color: "#34d399" }}>
                  {soldList[0]?.formatted_price || "No Confirmed Sale"}
                </strong>
                <span className="muted" style={{ fontSize: 11 }}>
                  {soldList[0]
                    ? `${soldList[0].source_domain || "Auction"} verified sale`
                    : "Asking prices ≠ sales"}
                </span>
              </div>
            </div>

            {ngEvidence?.checked && (
              <div
                className="list-item"
                style={{
                  padding: "7px 10px",
                  fontSize: 11.5,
                  borderLeft: ngEvidence.verified_local_listings_found
                    ? "3px solid #34d399"
                    : "3px solid #f59e0b",
                }}
              >
                <strong>Nigerian Regional Market Check: </strong>
                <span className="muted">{ngEvidence.note}</span>
              </div>
            )}
          </div>

          {/* Retrieved Product Specifications */}
          {specs.length > 0 && (
            <div
              style={{
                border: "1px solid var(--border-subtle, rgba(255,255,255,0.09))",
                borderRadius: 12,
                padding: "10px 12px",
                background: "rgba(255,255,255,0.02)",
              }}
            >
              <div className="eyebrow-mono" style={{ marginBottom: 6 }}>
                VERIFIED PRODUCT SPECIFICATIONS
              </div>
              <div className="grid-2" style={{ gap: 6 }}>
                {specs.slice(0, 6).map((sp) => (
                  <div key={sp.label} className="list-item" style={{ padding: "6px 9px" }}>
                    <div className="muted mono" style={{ fontSize: 10 }}>{sp.label.toUpperCase()}</div>
                    <div style={{ fontSize: 12.5, fontWeight: 600 }}>{sp.value}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 3. CLICKABLE PRODUCT & LISTING CARDS */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
          <div className="eyebrow-mono" style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <ShieldCheck size={12} /> CLICKABLE PRODUCT PAGES, DEALER LISTINGS &amp; AUCTION SOURCES ({filteredListings.length})
          </div>
          <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
            {(
              [
                { id: "ALL", label: `All (${listings.length})` },
                { id: "ASKING", label: "Active Listings / Asking" },
                { id: "SOLD", label: "Completed Sales" },
                { id: "MSRP", label: "MSRP / Reference" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`btn btn-sm ${activeFilter === tab.id ? "" : "btn-secondary"}`}
                onClick={() => setActiveFilter(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2" style={{ gap: 10 }}>
          {filteredListings.map((item, idx) => (
            <div
              key={item.url || idx}
              className="list-item"
              style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: 8,
                padding: "10px 12px",
                border: "1px solid var(--border-subtle, rgba(255,255,255,0.1))",
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div className="row-between" style={{ gap: 6, flexWrap: "wrap" }}>
                  <StatusIndicator
                    label={
                      item.is_completed_sale
                        ? "CONFIRMED COMPLETED SALE"
                        : item.price_type === "ORIGINAL_MSRP"
                        ? "ORIGINAL MSRP"
                        : item.price_type === "UNVERIFIED_CONVERTED_ESTIMATE"
                        ? "UNVERIFIED NGN ESTIMATE"
                        : "ASKING PRICE / LISTING"
                    }
                    tone={priceTypeTone(item.price_type)}
                  />
                  {item.advertised_price && (
                    <span
                      className="mono"
                      style={{
                        fontSize: 13.5,
                        fontWeight: 700,
                        color: item.is_completed_sale ? "#34d399" : "var(--accent, #38bdf8)",
                      }}
                    >
                      {item.advertised_price} {item.currency ? `(${item.currency})` : ""}
                    </span>
                  )}
                </div>

                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    color: "inherit",
                    textDecoration: "none",
                    fontWeight: 600,
                    fontSize: 13.5,
                    lineHeight: 1.35,
                  }}
                >
                  {item.title}
                </a>

                <div className="row" style={{ flexWrap: "wrap", gap: 6, fontSize: 11 }}>
                  <span className="pill mono">
                    <Globe size={10} style={{ verticalAlign: "middle", marginRight: 3 }} />
                    {item.domain}
                  </span>
                  {item.country && (
                    <span className="pill mono">
                      <MapPin size={10} style={{ verticalAlign: "middle", marginRight: 3 }} />
                      {item.country}
                    </span>
                  )}
                  {item.condition && <span className="pill mono">{item.condition}</span>}
                  {item.mileage && <span className="pill mono">{item.mileage}</span>}
                  {item.page_fetched && (
                    <span className="pill pill-cyan mono">FULL PAGE VERIFIED</span>
                  )}
                </div>

                {item.summary_excerpt && (
                  <div className="muted" style={{ fontSize: 12, lineHeight: 1.45 }}>
                    {item.summary_excerpt}
                  </div>
                )}
              </div>

              <div
                className="row-between"
                style={{
                  paddingTop: 6,
                  borderTop: "1px solid rgba(255,255,255,0.06)",
                  flexWrap: "wrap",
                  gap: 6,
                }}
              >
                <span className="muted mono" style={{ fontSize: 10.5 }}>
                  Checked {formatShortDate(item.last_checked_at)}
                </span>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary btn-sm"
                  style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }}
                >
                  Open Source Page <ExternalLink size={12} />
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
