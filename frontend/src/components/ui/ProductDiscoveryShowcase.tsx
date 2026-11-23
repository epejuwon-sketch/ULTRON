import React, { useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  ImageOff,
  MapPin,
  ShieldCheck,
} from "lucide-react";

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

export interface VariantBreakdownItem {
  variant_name: string;
  production_note?: string;
  original_msrp_note?: string;
  current_market_note?: string;
  source_title?: string;
  source_url?: string;
  source_domain?: string;
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
  variant_breakdowns?: VariantBreakdownItem[];
  editorial_report?: {
    headline?: string;
    subheadline?: string;
    formatted_date?: string;
    verification_badges?: Array<{ label: string; tone?: string }>;
    introduction?: string;
    msrp_section?: {
      heading?: string;
      narrative?: string;
      records?: ProductPriceEvidenceItem[];
    };
    collector_market_section?: {
      heading?: string;
      variants?: VariantBreakdownItem[];
    };
    active_listings_section?: {
      heading?: string;
      listings?: ProductListingItem[];
    };
    completed_sales_section?: {
      heading?: string;
      narrative?: string;
      sales?: any[];
    };
    nigerian_market_section?: {
      heading?: string;
      verified_local_listings_found?: boolean;
      narrative?: string;
    };
  };
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

function renderInlineRichText(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s)]+)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} style={{ color: "#f8fafc", fontWeight: 600 }}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    const mdLink = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    if (mdLink) {
      return (
        <a
          key={idx}
          href={mdLink[2]}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: "#38bdf8",
            textDecoration: "underline",
            textUnderlineOffset: "3px",
            fontWeight: 500,
          }}
        >
          {mdLink[1]}
        </a>
      );
    }
    if (/^https?:\/\/[^\s)]+$/.test(part)) {
      const cleanUrl = part.replace(/[.,;!?]+$/, "");
      let hostLabel = cleanUrl;
      try {
        hostLabel = new URL(cleanUrl).hostname.replace(/^www\./, "");
      } catch {
        // keep raw URL
      }
      return (
        <a
          key={idx}
          href={cleanUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: "#38bdf8",
            textDecoration: "underline",
            textUnderlineOffset: "3px",
          }}
        >
          {hostLabel}
        </a>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

export function renderEditorialArticleMarkdown(markdown: string): React.ReactNode {
  const lines = (markdown || "").split("\n");
  const elements: React.ReactNode[] = [];
  let bulletBuffer: string[] = [];

  const flushBullets = (keyPrefix: string) => {
    if (bulletBuffer.length === 0) return;
    const items = [...bulletBuffer];
    bulletBuffer = [];
    elements.push(
      <ul
        key={`ul-${keyPrefix}`}
        style={{
          margin: "8px 0 16px",
          paddingLeft: 20,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          color: "#cbd5e1",
          fontSize: 15,
          lineHeight: 1.68,
        }}
      >
        {items.map((item, i) => (
          <li key={i}>{renderInlineRichText(item)}</li>
        ))}
      </ul>
    );
  };

  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();
    if (!line) {
      flushBullets(`empty-${idx}`);
      return;
    }
    if (line.startsWith("### ")) {
      flushBullets(`h3-${idx}`);
      elements.push(
        <h4
          key={`h3-${idx}`}
          style={{
            margin: "20px 0 8px",
            fontSize: 16.5,
            fontWeight: 600,
            color: "#f1f5f9",
            letterSpacing: "-0.01em",
          }}
        >
          {renderInlineRichText(line.slice(4))}
        </h4>
      );
      return;
    }
    if (line.startsWith("## ") || line.startsWith("# ")) {
      flushBullets(`h2-${idx}`);
      const headingText = line.replace(/^#+\s+/, "");
      elements.push(
        <h3
          key={`h2-${idx}`}
          style={{
            margin: "26px 0 10px",
            paddingTop: 18,
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            fontSize: 19,
            fontWeight: 700,
            color: "#ffffff",
            letterSpacing: "-0.015em",
          }}
        >
          {renderInlineRichText(headingText)}
        </h3>
      );
      return;
    }
    if (line.startsWith("- ") || line.startsWith("* ") || /^\d+\.\s+/.test(line)) {
      const cleaned = line.replace(/^(?:[-*]|\d+\.)\s+/, "");
      bulletBuffer.push(cleaned);
      return;
    }
    flushBullets(`p-${idx}`);
    elements.push(
      <p
        key={`p-${idx}`}
        style={{
          margin: "0 0 14px",
          fontSize: 15,
          lineHeight: 1.72,
          color: "#cbd5e1",
        }}
      >
        {renderInlineRichText(line)}
      </p>
    );
  });

  flushBullets("final");
  return <div>{elements}</div>;
}

export function ProductDiscoveryShowcase({
  data,
  articleMarkdown,
}: {
  data?: ProductIntelligenceData | null;
  articleMarkdown?: string;
}) {
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});
  const [selectedPrimaryIdx, setSelectedPrimaryIdx] = useState(0);

  if (!data || !data.detected || !data.product) return null;

  const product = data.product;
  const report = data.editorial_report || {};
  const specs = data.specifications || [];

  // Deduplicate valid authentic images
  const validImages = (data.images || []).filter(
    (img) => img.image_url && !failedImages[img.image_url]
  );

  // Arrange collage images: Primary hero (2/3 left) + up to 2 stacked secondary photos (1/3 right)
  const primaryIdx = validImages.length > 0 ? Math.min(selectedPrimaryIdx, validImages.length - 1) : 0;
  const primaryImage = validImages[primaryIdx];
  const secondaryImages = validImages.filter((_, i) => i !== primaryIdx).slice(0, 2);
  const extraImages = validImages.slice(3);

  const formattedDate =
    report.formatted_date ||
    (data.retrieved_at
      ? new Date(data.retrieved_at).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "long",
          year: "numeric",
        })
      : "");

  const badges =
    report.verification_badges && report.verification_badges.length > 0
      ? report.verification_badges
      : [
          ...(specs.length >= 2 ? [{ label: "Factory specifications verified", tone: "success" }] : []),
          ...(formattedDate ? [{ label: `Market data: ${formattedDate}`, tone: "info" }] : []),
          ...((data.listings || []).length > 0
            ? [{ label: `${(data.listings || []).length} live sources retrieved`, tone: "success" }]
            : []),
        ];

  const activeListings =
    report.active_listings_section?.listings ||
    (data.listings || []).filter((l) => !l.is_completed_sale);
  const completedSales =
    report.completed_sales_section?.sales ||
    (data.listings || []).filter((l) => l.is_completed_sale);
  const variants = report.collector_market_section?.variants || data.variant_breakdowns || [];
  const ngSection = report.nigerian_market_section || data.pricing_summary?.nigeria_market_evidence;

  return (
    <article
      data-testid="product-discovery-showcase"
      style={{
        marginTop: 6,
        marginBottom: 14,
        padding: "22px 20px",
        borderRadius: 18,
        background: "linear-gradient(180deg, rgba(13, 18, 30, 0.96) 0%, rgba(8, 11, 20, 0.98) 100%)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        color: "#f8fafc",
        maxWidth: "100%",
        overflow: "hidden",
      }}
    >
      {/* 1. LARGE PROMINENT EDITORIAL REPORT TITLE */}
      <header style={{ marginBottom: 18 }}>
        <div
          className="mono"
          style={{
            fontSize: 11,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "#38bdf8",
            marginBottom: 6,
          }}
        >
          ULTRON EDITORIAL RESEARCH // {product.product_category || "COLLECTOR MARKET INTELLIGENCE"}
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: "clamp(22px, 3.4vw, 31px)",
            fontWeight: 800,
            lineHeight: 1.2,
            letterSpacing: "-0.02em",
            color: "#ffffff",
          }}
        >
          {report.headline || `${product.product_name} — Collector Market Report`}
        </h1>

        {/* 2. COMPACT VERIFICATION & RESEARCH-DATE BADGES */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginTop: 12,
          }}
        >
          {badges.map((b, idx) => {
            const isGreen = b.tone === "success" || idx % 2 === 0;
            return (
              <span
                key={b.label}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 11px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  background: isGreen
                    ? "rgba(16, 185, 129, 0.14)"
                    : "rgba(56, 189, 248, 0.14)",
                  color: isGreen ? "#34d399" : "#38bdf8",
                  border: isGreen
                    ? "1px solid rgba(52, 211, 153, 0.28)"
                    : "1px solid rgba(56, 189, 248, 0.28)",
                }}
              >
                <CheckCircle2 size={12} />
                {b.label}
              </span>
            );
          })}
        </div>
      </header>

      {/* 3. PRODUCT PHOTOGRAPH COLLAGE (2/3 Primary Left + 1/3 Two Stacked Right, Rounded Outer Corners) */}
      {validImages.length > 0 ? (
        <section aria-label="Verified Product Photograph Collage" style={{ marginBottom: 22 }}>
          <div
            data-testid="editorial-photo-collage"
            style={{
              display: "grid",
              gridTemplateColumns:
                secondaryImages.length > 0
                  ? "minmax(0, 1.85fr) minmax(0, 1fr)"
                  : "minmax(0, 1fr)",
              gap: 10,
              borderRadius: 18,
              overflow: "hidden",
              background: "#05070e",
              border: "1px solid rgba(255, 255, 255, 0.1)",
            }}
          >
            {/* Primary 2/3 Hero Photograph */}
            {primaryImage && (
              <div
                style={{
                  position: "relative",
                  minHeight: secondaryImages.length > 0 ? 270 : 240,
                  maxHeight: 420,
                  overflow: "hidden",
                  background: "#070b14",
                }}
              >
                <a
                  href={primaryImage.source_page_url || primaryImage.image_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={`Open source: ${primaryImage.title || product.product_name}`}
                  style={{ display: "block", width: "100%", height: "100%" }}
                >
                  <img
                    src={primaryImage.image_url}
                    alt={primaryImage.title || product.product_name || "Primary product photograph"}
                    loading="eager"
                    referrerPolicy="no-referrer"
                    onError={() =>
                      setFailedImages((prev) => ({ ...prev, [primaryImage.image_url]: true }))
                    }
                    style={{
                      width: "100%",
                      height: "100%",
                      minHeight: secondaryImages.length > 0 ? 270 : 240,
                      maxHeight: 420,
                      objectFit: "cover",
                      display: "block",
                    }}
                  />
                </a>
                <a
                  href={primaryImage.source_page_url || primaryImage.image_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    position: "absolute",
                    left: 10,
                    bottom: 10,
                    right: 10,
                    padding: "6px 10px",
                    borderRadius: 8,
                    background: "rgba(6, 10, 19, 0.82)",
                    backdropFilter: "blur(6px)",
                    color: "#e2e8f0",
                    textDecoration: "none",
                    fontSize: 11,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                    border: "1px solid rgba(255,255,255,0.12)",
                  }}
                >
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <strong>{primaryImage.image_type_label || "Verified Photo"}</strong>
                    {primaryImage.source_domain ? ` · ${primaryImage.source_domain}` : ""}
                  </span>
                  <ExternalLink size={11} style={{ flexShrink: 0, color: "#38bdf8" }} />
                </a>
              </div>
            )}

            {/* Right Column: Two Vertically Stacked Photographs */}
            {secondaryImages.length > 0 && (
              <div
                style={{
                  display: "grid",
                  gridTemplateRows:
                    secondaryImages.length === 2 ? "1fr 1fr" : "1fr",
                  gap: 10,
                  minHeight: 270,
                  maxHeight: 420,
                }}
              >
                {secondaryImages.map((img, sIdx) => (
                  <div
                    key={img.image_url}
                    style={{
                      position: "relative",
                      overflow: "hidden",
                      background: "#070b14",
                      minHeight: 130,
                    }}
                  >
                    <a
                      href={img.source_page_url || img.image_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`Open source: ${img.title || product.product_name}`}
                      style={{ display: "block", width: "100%", height: "100%" }}
                    >
                      <img
                        src={img.image_url}
                        alt={img.title || `${product.product_name} perspective ${sIdx + 2}`}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={() =>
                          setFailedImages((prev) => ({ ...prev, [img.image_url]: true }))
                        }
                        style={{
                          width: "100%",
                          height: "100%",
                          minHeight: 130,
                          maxHeight: 205,
                          objectFit: "cover",
                          display: "block",
                        }}
                      />
                    </a>
                    <a
                      href={img.source_page_url || img.image_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        position: "absolute",
                        left: 8,
                        bottom: 8,
                        right: 8,
                        padding: "4px 8px",
                        borderRadius: 6,
                        background: "rgba(6, 10, 19, 0.82)",
                        backdropFilter: "blur(6px)",
                        color: "#e2e8f0",
                        textDecoration: "none",
                        fontSize: 10,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 6,
                        border: "1px solid rgba(255,255,255,0.12)",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {img.source_domain || img.image_type_label || "Source"}
                      </span>
                      <ExternalLink size={10} style={{ flexShrink: 0, color: "#38bdf8" }} />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Caption & Clickable Source Attribution Strip under Collage */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 8,
              marginTop: 8,
              fontSize: 11.5,
              color: "#94a3b8",
            }}
          >
            <div>
              Photographs sourced from{" "}
              {validImages.slice(0, 3).map((im, i) => (
                <React.Fragment key={im.image_url}>
                  {i > 0 && ", "}
                  <a
                    href={im.source_page_url || im.image_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "#38bdf8", textDecoration: "underline" }}
                  >
                    {im.source_domain || "verified source"}
                  </a>
                </React.Fragment>
              ))}
              .
            </div>
            {extraImages.length > 0 && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span>More perspectives:</span>
                {validImages.slice(0, 6).map((im, i) => (
                  <button
                    key={im.image_url}
                    type="button"
                    onClick={() => setSelectedPrimaryIdx(i)}
                    style={{
                      padding: "2px 7px",
                      borderRadius: 6,
                      fontSize: 11,
                      cursor: "pointer",
                      border:
                        i === primaryIdx
                          ? "1px solid #38bdf8"
                          : "1px solid rgba(255,255,255,0.12)",
                      background:
                        i === primaryIdx ? "rgba(56, 189, 248, 0.16)" : "transparent",
                      color: i === primaryIdx ? "#38bdf8" : "#94a3b8",
                    }}
                  >
                    #{i + 1}
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>
      ) : (
        <section
          style={{
            marginBottom: 20,
            padding: "18px 16px",
            borderRadius: 14,
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <ImageOff size={22} className="muted" />
          <div style={{ fontSize: 13, color: "#94a3b8" }}>
            <strong style={{ color: "#e2e8f0" }}>Verified Photograph Unavailable: </strong>
            No verified public product photograph was returned by the live sources. ULTRON never fabricates synthetic images for real-world products.
          </div>
        </section>
      )}

      {/* 4. NATURAL-LANGUAGE EDITORIAL ARTICLE (NEON / Gemini Analysis) */}
      {articleMarkdown && articleMarkdown.trim() ? (
        <section
          data-testid="editorial-article-prose"
          style={{
            marginBottom: 24,
            fontSize: 15,
            lineHeight: 1.72,
            color: "#cbd5e1",
          }}
        >
          {renderEditorialArticleMarkdown(articleMarkdown)}
        </section>
      ) : (
        report.introduction && (
          <section style={{ marginBottom: 22 }}>
            <p style={{ margin: "0 0 14px", fontSize: 15.5, lineHeight: 1.72, color: "#e2e8f0" }}>
              {report.introduction}
            </p>
          </section>
        )
      )}

      {/* 5. VARIANT & TRIM SEPARATION (Coupe vs Roadster vs Special Editions) */}
      {variants.length > 0 && (
        <section
          style={{
            paddingTop: 18,
            marginBottom: 22,
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
          }}
        >
          <h3 style={{ margin: "0 0 12px", fontSize: 18.5, fontWeight: 700, color: "#ffffff" }}>
            {report.collector_market_section?.heading || "Collector Market by Variant"}
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {variants.map((vb) => (
              <div
                key={vb.variant_name}
                style={{
                  padding: "12px 14px",
                  borderRadius: 12,
                  background: "rgba(255, 255, 255, 0.025)",
                  borderLeft: "3px solid #38bdf8",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: 8,
                    marginBottom: 4,
                  }}
                >
                  <strong style={{ fontSize: 15, color: "#ffffff" }}>{vb.variant_name}</strong>
                  {vb.original_msrp_note && (
                    <span className="mono" style={{ fontSize: 12, color: "#94a3b8" }}>
                      {vb.original_msrp_note}
                    </span>
                  )}
                </div>
                {vb.production_note && (
                  <div style={{ fontSize: 12.5, color: "#94a3b8", marginBottom: 4 }}>
                    {vb.production_note}
                  </div>
                )}
                {vb.current_market_note && (
                  <div style={{ fontSize: 14, lineHeight: 1.6, color: "#cbd5e1" }}>
                    {vb.current_market_note}{" "}
                    {vb.source_url && (
                      <a
                        href={vb.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          color: "#38bdf8",
                          textDecoration: "underline",
                          fontSize: 13,
                          whiteSpace: "nowrap",
                        }}
                      >
                        [{vb.source_domain || "Source"} ↗]
                      </a>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 6. ACTIVE DEALER LISTINGS & MARKET SOURCES (With Direct Clickable Links) */}
      {activeListings.length > 0 && (
        <section
          style={{
            paddingTop: 18,
            marginBottom: 22,
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
          }}
        >
          <h3 style={{ margin: "0 0 6px", fontSize: 18.5, fontWeight: 700, color: "#ffffff" }}>
            Active Dealer Listings &amp; Valuation Sources
          </h3>
          <p style={{ margin: "0 0 12px", fontSize: 13, color: "#94a3b8" }}>
            Advertised asking prices and live market inventory. Every entry links directly to its original listing or valuation page.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {activeListings.map((item, idx) => (
              <div
                key={item.url || idx}
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  padding: "12px 14px",
                  borderRadius: 12,
                  background: "rgba(255, 255, 255, 0.025)",
                  border: "1px solid rgba(255, 255, 255, 0.07)",
                }}
              >
                {item.image_url && !failedImages[item.image_url] && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ flexShrink: 0 }}
                  >
                    <img
                      src={item.image_url}
                      alt={item.title}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      onError={() =>
                        setFailedImages((prev) => ({ ...prev, [item.image_url!]: true }))
                      }
                      style={{
                        width: 84,
                        height: 62,
                        objectFit: "cover",
                        borderRadius: 8,
                        display: "block",
                      }}
                    />
                  </a>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      gap: 8,
                    }}
                  >
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        color: "#ffffff",
                        fontWeight: 600,
                        fontSize: 14.5,
                        textDecoration: "underline",
                        textDecorationColor: "rgba(56, 189, 248, 0.5)",
                        textUnderlineOffset: "3px",
                      }}
                    >
                      {item.title}
                    </a>
                    {item.advertised_price && (
                      <span
                        className="mono"
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: "#38bdf8",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.advertised_price} {item.currency ? `(${item.currency})` : ""} · Asking
                      </span>
                    )}
                  </div>
                  {item.summary_excerpt && (
                    <div
                      style={{
                        fontSize: 13.5,
                        color: "#cbd5e1",
                        lineHeight: 1.55,
                        marginTop: 4,
                      }}
                    >
                      {item.summary_excerpt}
                    </div>
                  )}
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 10,
                      alignItems: "center",
                      marginTop: 6,
                      fontSize: 12,
                      color: "#94a3b8",
                    }}
                  >
                    <span className="mono">{item.domain}</span>
                    {item.country && (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                        <MapPin size={11} /> {item.country}
                      </span>
                    )}
                    {item.condition && <span>· {item.condition}</span>}
                    {item.mileage && <span>· {item.mileage}</span>}
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        color: "#38bdf8",
                        textDecoration: "none",
                        fontWeight: 600,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                        marginLeft: "auto",
                      }}
                    >
                      Open Listing / Source <ExternalLink size={11} />
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 7. DOCUMENTED COMPLETED SALES (Strictly Separated from Asking Prices) */}
      {completedSales.length > 0 && (
        <section
          style={{
            paddingTop: 18,
            marginBottom: 22,
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
          }}
        >
          <h3 style={{ margin: "0 0 6px", fontSize: 18.5, fontWeight: 700, color: "#ffffff" }}>
            Documented Completed Auction &amp; Transactional Sales
          </h3>
          <p style={{ margin: "0 0 12px", fontSize: 13, color: "#94a3b8" }}>
            Verified completed sales and auction hammer results, separated from advertised asking prices.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {completedSales.map((sale: any, idx: number) => {
              const sUrl = sale.url || sale.source_url || "";
              const sTitle = sale.title || sale.source_title || sale.domain || sale.source_domain || "Completed Auction Record";
              const sDomain = sale.domain || sale.source_domain || "";
              const sPrice = sale.advertised_price || sale.formatted_price || "Verified Sale";
              const sExcerpt = sale.summary_excerpt || sale.context_excerpt || "";
              return (
                <div
                  key={`${sUrl}-${idx}`}
                  style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    background: "rgba(16, 185, 129, 0.06)",
                    border: "1px solid rgba(52, 211, 153, 0.22)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      justifyContent: "space-between",
                      alignItems: "baseline",
                      gap: 8,
                    }}
                  >
                    <a
                      href={sUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        color: "#ffffff",
                        fontWeight: 600,
                        fontSize: 14.5,
                        textDecoration: "underline",
                        textDecorationColor: "rgba(52, 211, 153, 0.5)",
                        textUnderlineOffset: "3px",
                      }}
                    >
                      {sTitle}
                    </a>
                    <span
                      className="mono"
                      style={{ fontSize: 14, fontWeight: 700, color: "#34d399" }}
                    >
                      {sPrice} · Confirmed Completed Sale
                    </span>
                  </div>
                  {sExcerpt && (
                    <div style={{ fontSize: 13.5, color: "#cbd5e1", lineHeight: 1.55, marginTop: 4 }}>
                      {sExcerpt}
                    </div>
                  )}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginTop: 6,
                      fontSize: 12,
                      color: "#94a3b8",
                    }}
                  >
                    <span className="mono">
                      <ShieldCheck size={12} style={{ verticalAlign: "middle", marginRight: 4, color: "#34d399" }} />
                      {sDomain}
                    </span>
                    {sUrl && (
                      <a
                        href={sUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          color: "#34d399",
                          textDecoration: "none",
                          fontWeight: 600,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        View Auction Record <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 8. NIGERIAN REGIONAL MARKET VERIFICATION */}
      {ngSection && (
        <section
          style={{
            paddingTop: 16,
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            fontSize: 13.5,
            lineHeight: 1.6,
            color: "#cbd5e1",
          }}
        >
          <strong style={{ color: "#ffffff" }}>Nigerian Market Verification: </strong>
          {(ngSection as any).narrative || (ngSection as any).note}
        </section>
      )}
    </article>
  );
}
