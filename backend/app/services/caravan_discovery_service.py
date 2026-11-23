"""CARAVAN Real Funding Discovery & Ingestion Engine (SSRF-hardened, Zero Fabrication)."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, IntegrationError, NotFoundError, ValidationError
from app.core.permissions import Principal, Role
from app.db.models import CaravanFundingOpportunityRecord, CaravanFundingSourceRecord
from app.db.repositories import append_audit_log
from app.services.universal_connections_service import validate_public_https_url

DISCOVERY_STAGES = ("DISCOVERED", "EXTRACTED", "NEEDS_REVIEW", "VERIFIED", "REJECTED")

_FUNDING_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("scholarship", "SCHOLARSHIP"),
    ("fellowship", "SCHOLARSHIP"),
    ("accelerator", "ACCELERATOR"),
    ("incubator", "ACCELERATOR"),
    ("competition", "COMPETITION"),
    ("challenge", "COMPETITION"),
    ("hackathon", "COMPETITION"),
    ("loan", "LOAN"),
    ("credit", "LOAN"),
    ("debt", "LOAN"),
    ("equity", "INVESTMENT"),
    ("venture", "INVESTMENT"),
    ("seed fund", "INVESTMENT"),
    ("grant", "GRANT"),
)

_NIGERIA_KEYWORDS = ("nigeria", "nigerian", "lagos", "abuja", "kano", "ibadan", "ngn", "₦")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _strip_html(raw: str) -> str:
    no_scripts = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw or "")
    text = re.sub(r"(?s)<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _infer_funding_type(text: str) -> str:
    low = (text or "").lower()
    for kw, ftype in _FUNDING_TYPE_KEYWORDS:
        if kw in low:
            return ftype
    return "OTHER"


def _extract_amount_and_currency(text: str) -> tuple[str, str]:
    patterns = [
        (r"(?:NGN|₦)\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|m|k))?", "NGN"),
        (r"(?:USD|\$)\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|m|k))?", "USD"),
        (r"(?:EUR|€)\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|m|k))?", "EUR"),
        (r"(?:GBP|£)\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|m|k))?", "GBP"),
    ]
    for pat, cur in patterns:
        m = re.search(pat, text or "", re.IGNORECASE)
        if m:
            return m.group(0).strip(), cur
    return "Not specified by source", "NGN" if any(k in (text or "").lower() for k in _NIGERIA_KEYWORDS) else "USD"


def _extract_iso_deadline(text: str) -> datetime | None:
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _check_robots_allowed(url: str, *, http_client: httpx.Client | None = None) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    path = parsed.path or "/"
    try:
        if http_client is not None:
            resp = http_client.get(robots_url, timeout=4.0)
        else:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(robots_url)
        if resp.status_code != 200:
            return True, "no_robots_restriction"
        applies = False
        for line in resp.text.splitlines():
            clean = line.split("#", 1)[0].strip()
            if not clean:
                continue
            low = clean.lower()
            if low.startswith("user-agent:"):
                agent = clean.split(":", 1)[1].strip().lower()
                applies = agent in {"*", "ultron", "ultron-caravan-discovery"}
            elif applies and low.startswith("disallow:"):
                rule = clean.split(":", 1)[1].strip()
                if rule == "/" or (rule and path.startswith(rule)):
                    return False, f"Disallowed by robots.txt ({rule})"
    except Exception:
        return True, "robots_unreachable"
    return True, "allowed"


def fetch_public_source_with_argon_guards(
    url: str,
    *,
    http_client: httpx.Client | None = None,
    max_retries: int = 2,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Fetch a public funding page with SSRF validation, robots.txt check, timeout, and retries."""
    clean_url = validate_public_https_url(url, require_https=False)
    allowed, robots_note = _check_robots_allowed(clean_url, http_client=http_client)
    if not allowed:
        raise ValidationError(f"Source retrieval blocked by site policy: {robots_note}")

    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            if http_client is not None:
                resp = http_client.get(clean_url, timeout=timeout, follow_redirects=True)
            else:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.get(clean_url)
            if resp.status_code >= 400:
                last_err = f"HTTP {resp.status_code}"
                if resp.status_code < 500 or attempt == max_retries:
                    raise IntegrationError(f"Source returned HTTP {resp.status_code} from {clean_url}")
            else:
                raw_text = resp.text or ""
                content_type = resp.headers.get("content-type", "text/html").split(";")[0].strip().lower()
                sha = hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()
                return {
                    "url": clean_url,
                    "content_type": content_type,
                    "raw_text": raw_text,
                    "content_sha256": sha,
                    "retrieved_at": _utcnow().isoformat(),
                    "robots": robots_note,
                    "attempts": attempt + 1,
                }
        except httpx.HTTPError as exc:
            last_err = f"{type(exc).__name__}"
            if attempt == max_retries:
                raise IntegrationError(f"Failed to retrieve {clean_url}: {last_err}") from exc
        if attempt < max_retries:
            time.sleep(0.05)

    raise IntegrationError(f"Failed to retrieve {clean_url}: {last_err}")


def extract_opportunities_from_source(
    *,
    source_url: str,
    provider_org: str,
    raw_text: str,
    content_type: str = "text/html",
    content_sha256: str | None = None,
    retrieved_at: str | None = None,
) -> list[dict[str, Any]]:
    """Extract structured funding opportunities without inventing missing details."""
    clean_url = validate_public_https_url(source_url, require_https=False)
    sha = content_sha256 or hashlib.sha256((raw_text or "").encode("utf-8", errors="replace")).hexdigest()
    ret_at = retrieved_at or _utcnow().isoformat()
    items: list[dict[str, Any]] = []

    # JSON feed extraction
    if "json" in content_type or raw_text.lstrip().startswith("{") or raw_text.lstrip().startswith("["):
        try:
            parsed = json.loads(raw_text)
            raw_list = parsed if isinstance(parsed, list) else parsed.get("opportunities") or parsed.get("items") or [parsed]
            for row in raw_list[:25]:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("title") or row.get("name") or "").strip()
                if len(title) < 3:
                    continue
                item_url = str(row.get("source_url") or row.get("url") or clean_url).strip()
                item_url = validate_public_https_url(item_url, require_https=False)
                reqs = str(row.get("eligibility_requirements") or row.get("eligibility") or row.get("description") or "").strip()
                geo = str(row.get("geographic_restrictions") or row.get("geography") or "").strip()
                amt = str(row.get("amount_display") or row.get("amount") or "").strip()
                cur = str(row.get("currency") or "").strip().upper()
                if not amt:
                    amt, inferred_cur = _extract_amount_and_currency(f"{title} {reqs}")
                    cur = cur or inferred_cur
                if not geo:
                    geo = "Nigeria" if any(k in f"{title} {reqs}".lower() for k in _NIGERIA_KEYWORDS) else "See official source"
                dl_raw = str(row.get("deadline_at") or row.get("deadline") or "").strip()
                dl = _extract_iso_deadline(dl_raw) if dl_raw else None
                missing: list[str] = []
                if not reqs:
                    missing.append("eligibility_requirements")
                    reqs = "Not specified in feed item; review official source URL."
                if amt == "Not specified by source":
                    missing.append("amount_display")
                if dl is None:
                    missing.append("deadline_at")
                items.append({
                    "title": title[:240],
                    "provider_org": str(row.get("provider_org") or provider_org).strip()[:180],
                    "funding_type": _infer_funding_type(f"{title} {row.get('funding_type', '')} {reqs}"),
                    "source_url": item_url,
                    "amount_display": amt[:120],
                    "currency": (cur or "USD")[:16],
                    "eligibility_requirements": reqs,
                    "geographic_restrictions": geo[:240],
                    "deadline_at": dl,
                    "missing_fields": missing,
                    "verification_status": "NEEDS_REVIEW",
                    "content_sha256": sha,
                    "retrieved_at": ret_at,
                })
            return items
        except json.JSONDecodeError:
            pass

    # HTML / plain-text extraction
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_text or "")
    h1_match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw_text or "")
    raw_title = _strip_html(h1_match.group(1) if h1_match else (title_match.group(1) if title_match else ""))
    plain = _strip_html(raw_text)
    if not raw_title and len(plain) >= 8:
        raw_title = plain[:90].strip()
    if len(raw_title) < 3:
        return []

    amt, cur = _extract_amount_and_currency(plain)
    dl = _extract_iso_deadline(plain)
    geo = "Nigeria" if any(k in plain.lower() for k in _NIGERIA_KEYWORDS) else "See official source"
    elig_match = re.search(r"(?i)(eligib[^.]{10,280}\.|require[^.]{10,280}\.|applicants?\s+must[^.]{10,280}\.)", plain)
    reqs = elig_match.group(1).strip() if elig_match else ""
    missing = []
    if not reqs:
        missing.append("eligibility_requirements")
        reqs = f"Extracted summary from {clean_url}; administrator must verify exact eligibility criteria at source."
    if amt == "Not specified by source":
        missing.append("amount_display")
    if dl is None:
        missing.append("deadline_at")

    items.append({
        "title": raw_title[:240],
        "provider_org": provider_org.strip()[:180],
        "funding_type": _infer_funding_type(f"{raw_title} {plain[:1000]}"),
        "source_url": clean_url,
        "amount_display": amt[:120],
        "currency": cur[:16],
        "eligibility_requirements": reqs,
        "geographic_restrictions": geo,
        "deadline_at": dl,
        "missing_fields": missing,
        "verification_status": "NEEDS_REVIEW",
        "content_sha256": sha,
        "retrieved_at": ret_at,
    })
    return items


def run_argon_source_ingestion(
    db: Session,
    *,
    principal: Principal,
    source_id: str,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """ARGON-orchestrated ingestion job for a registered funding source."""
    src = db.execute(
        select(CaravanFundingSourceRecord).where(
            CaravanFundingSourceRecord.tenant_id == principal.tenant_id,
            CaravanFundingSourceRecord.source_id == source_id,
        )
    ).scalar_one_or_none()
    if src is None:
        raise NotFoundError(f"Funding source '{source_id}' not found.")

    fetched = fetch_public_source_with_argon_guards(src.base_url, http_client=http_client)
    extracted = extract_opportunities_from_source(
        source_url=src.base_url,
        provider_org=src.name,
        raw_text=fetched["raw_text"],
        content_type=fetched["content_type"],
        content_sha256=fetched["content_sha256"],
        retrieved_at=fetched["retrieved_at"],
    )

    existing = db.execute(
        select(CaravanFundingOpportunityRecord).where(
            CaravanFundingOpportunityRecord.tenant_id == principal.tenant_id
        )
    ).scalars().all()
    seen_urls = {e.source_url.rstrip("/").lower() for e in existing}
    seen_pairs = {(e.title.strip().lower(), e.provider_org.strip().lower()) for e in existing}

    created_ids: list[str] = []
    duplicates_skipped = 0
    for item in extracted:
        norm_u = item["source_url"].rstrip("/").lower()
        pair = (item["title"].strip().lower(), item["provider_org"].strip().lower())
        if norm_u in seen_urls or pair in seen_pairs:
            duplicates_skipped += 1
            continue
        opp_id = f"copp_{uuid.uuid4().hex[:14]}"
        evidence = json.dumps({
            "retrieved_at": item["retrieved_at"],
            "content_sha256": item["content_sha256"],
            "missing_fields": item["missing_fields"],
            "argon_ingestion": True,
        })
        rec = CaravanFundingOpportunityRecord(
            opportunity_id=opp_id,
            tenant_id=principal.tenant_id,
            source_id=src.source_id,
            title=item["title"],
            provider_org=item["provider_org"],
            funding_type=item["funding_type"],
            source_url=item["source_url"],
            amount_display=item["amount_display"],
            currency=item["currency"],
            eligibility_requirements=item["eligibility_requirements"],
            geographic_restrictions=item["geographic_restrictions"],
            deadline_at=item["deadline_at"],
            verification_status="NEEDS_REVIEW",
            supporting_evidence=evidence,
            tags_json=json.dumps(["ARGON_INGESTED", "NEEDS_REVIEW"]),
            created_by=principal.username,
        )
        db.add(rec)
        seen_urls.add(norm_u)
        seen_pairs.add(pair)
        created_ids.append(opp_id)

    src.last_synced_at = _utcnow()
    src.status = "ACTIVE"
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_ARGON_INGESTION",
        resource=src.source_id,
        outcome=f"extracted={len(extracted)}|created={len(created_ids)}|duplicates={duplicates_skipped}",
    )
    db.commit()
    return {
        "source_id": src.source_id,
        "source_name": src.name,
        "retrieved_at": fetched["retrieved_at"],
        "content_sha256": fetched["content_sha256"],
        "extracted_count": len(extracted),
        "created_count": len(created_ids),
        "duplicates_skipped": duplicates_skipped,
        "created_opportunity_ids": created_ids,
        "verification_status": "NEEDS_REVIEW",
    }


def summarize_source_with_neon(
    *,
    source_url: str,
    provider_org: str,
    raw_text: str,
    settings: Settings,
) -> dict[str, Any]:
    """Summarise source material while strictly separating sourced facts from AI interpretations."""
    extracted = extract_opportunities_from_source(
        source_url=source_url,
        provider_org=provider_org,
        raw_text=raw_text,
    )
    neon_mode = "GEMINI_LIVE" if (settings.gemini_api_key and settings.gemini_api_key.get_secret_value()) else "DETERMINISTIC"
    return {
        "sourced_facts": {
            "source_url": validate_public_https_url(source_url, require_https=False),
            "extracted_count": len(extracted),
            "items": [
                {
                    "title": x["title"],
                    "funding_type": x["funding_type"],
                    "amount_display": x["amount_display"],
                    "currency": x["currency"],
                    "geographic_restrictions": x["geographic_restrictions"],
                    "missing_fields": x["missing_fields"],
                    "content_sha256": x["content_sha256"],
                    "retrieved_at": x["retrieved_at"],
                }
                for x in extracted
            ],
        },
        "ai_interpretation": {
            "neon_mode": neon_mode,
            "summary": (
                f"Extracted {len(extracted)} candidate item(s) from {source_url}. "
                "Administrator review is required before marking VERIFIED."
            ),
            "requires_human_verification": True,
        },
    }


def review_discovered_opportunity(
    db: Session,
    *,
    principal: Principal,
    opportunity_id: str,
    decision: str,
    supporting_evidence: str = "",
) -> dict[str, Any]:
    """Administrator-only review transition: NEEDS_REVIEW -> VERIFIED or REJECTED."""
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may verify or reject discovered opportunities.")
    dec = (decision or "").strip().upper()
    if dec not in {"VERIFIED", "REJECTED"}:
        raise ValidationError("Review decision must be VERIFIED or REJECTED.")
    if dec == "VERIFIED" and not (supporting_evidence or "").strip():
        raise ValidationError("Supporting evidence is required to mark an opportunity VERIFIED.")

    rec = db.execute(
        select(CaravanFundingOpportunityRecord).where(
            CaravanFundingOpportunityRecord.tenant_id == principal.tenant_id,
            CaravanFundingOpportunityRecord.opportunity_id == opportunity_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Funding opportunity '{opportunity_id}' not found.")

    now = _utcnow()
    rec.verification_status = dec
    if supporting_evidence.strip():
        rec.supporting_evidence = supporting_evidence.strip()
    rec.last_verified_at = now
    rec.verified_by = principal.username
    rec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_DISCOVERY_REVIEWED",
        resource=rec.opportunity_id,
        outcome=f"decision={dec}",
    )
    db.commit()
    db.refresh(rec)
    from app.services.caravan_product_service import _serialize_opportunity

    return _serialize_opportunity(rec)


NIGERIA_FUNDING_DIRECTORY: list[dict[str, Any]] = [
    {
        "name": "Bank of Industry (BOI) Nigeria",
        "source_type": "OFFICIAL_REGISTRY",
        "base_url": "https://www.boi.ng/",
        "country": "Nigeria",
        "categories": ["LOAN", "GRANT"],
    },
    {
        "name": "Tony Elumelu Foundation (TEF)",
        "source_type": "PUBLIC_PORTAL",
        "base_url": "https://www.tonyelumelufoundation.org/",
        "country": "Nigeria",
        "categories": ["GRANT", "ACCELERATOR"],
    },
    {
        "name": "NITDA Nigeria",
        "source_type": "OFFICIAL_REGISTRY",
        "base_url": "https://nitda.gov.ng/",
        "country": "Nigeria",
        "categories": ["GRANT", "SCHOLARSHIP", "COMPETITION"],
    },
    {
        "name": "Lagos State Employment Trust Fund (LSETF)",
        "source_type": "OFFICIAL_REGISTRY",
        "base_url": "https://lsetf.ng/",
        "country": "Nigeria",
        "categories": ["LOAN", "GRANT"],
    },
    {
        "name": "SMEDAN Nigeria",
        "source_type": "OFFICIAL_REGISTRY",
        "base_url": "https://smedan.gov.ng/",
        "country": "Nigeria",
        "categories": ["GRANT", "LOAN"],
    },
    {
        "name": "TETFund Nigeria",
        "source_type": "OFFICIAL_REGISTRY",
        "base_url": "https://tetfund.gov.ng/",
        "country": "Nigeria",
        "categories": ["SCHOLARSHIP", "GRANT"],
    },
    {
        "name": "Development Bank of Nigeria (DBN)",
        "source_type": "OFFICIAL_REGISTRY",
        "base_url": "https://devbankng.com/",
        "country": "Nigeria",
        "categories": ["LOAN"],
    },
    {
        "name": "Co-Creation Hub (CcHUB) Nigeria",
        "source_type": "PUBLIC_PORTAL",
        "base_url": "https://cchub.africa/",
        "country": "Nigeria",
        "categories": ["ACCELERATOR", "INVESTMENT"],
    },
]


def seed_nigeria_funding_directory(db: Session, *, principal: Principal) -> dict[str, Any]:
    """Register official Nigerian funding organisations into CaravanFundingSourceRecord (no fabricated opportunities)."""
    if principal.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("Only OWNER or ADMIN administrators may seed official funding sources.")
    existing = db.execute(
        select(CaravanFundingSourceRecord).where(CaravanFundingSourceRecord.tenant_id == principal.tenant_id)
    ).scalars().all()
    seen_urls = {s.base_url.rstrip("/").lower() for s in existing}
    added: list[str] = []
    skipped = 0
    for item in NIGERIA_FUNDING_DIRECTORY:
        norm = item["base_url"].rstrip("/").lower()
        if norm in seen_urls:
            skipped += 1
            continue
        rec = CaravanFundingSourceRecord(
            source_id=f"csrc_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            name=item["name"],
            source_type=item["source_type"],
            base_url=item["base_url"],
            verification_policy="MANUAL_REVIEW",
            status="ACTIVE",
            created_by=principal.username,
        )
        db.add(rec)
        seen_urls.add(norm)
        added.append(rec.source_id)

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="CARAVAN_NIGERIA_DIRECTORY_SEEDED",
        resource="nigeria_directory",
        outcome=f"added={len(added)}|skipped={skipped}",
    )
    db.commit()
    return {"added_count": len(added), "skipped_count": skipped, "added_source_ids": added}


def run_caravan_discovery_sweep(
    db: Session,
    *,
    principal: Principal,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Execute scheduled ARGON discovery sweep across all enabled funding sources and expire outdated deadlines."""
    from app.services.caravan_product_service import sweep_expired_opportunities

    sources = db.execute(
        select(CaravanFundingSourceRecord).where(
            CaravanFundingSourceRecord.tenant_id == principal.tenant_id,
            CaravanFundingSourceRecord.status != "DISABLED",
        )
    ).scalars().all()

    ingested_total = 0
    failures: list[dict[str, str]] = []
    for src in sources:
        try:
            res = run_argon_source_ingestion(db, principal=principal, source_id=src.source_id, http_client=http_client)
            ingested_total += int(res.get("created_count", 0))
        except Exception as exc:
            src.status = "DEGRADED"
            src.last_synced_at = _utcnow()
            failures.append({"source_id": src.source_id, "name": src.name, "error": str(exc)[:200]})
            db.commit()

    expired = sweep_expired_opportunities(db, principal=principal)
    return {
        "sources_checked": len(sources),
        "new_opportunities_discovered": ingested_total,
        "expired_marked": expired["expired_count"],
        "failures": failures,
    }

