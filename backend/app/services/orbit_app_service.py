"""ORBIT 2.0 Universal Device Application Registry, Resolver & Permission Service."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.db.models import DeviceAppPermissionRecord, DeviceRecord, OrbitRegisteredAppRecord
from app.db.repositories import append_audit_log
from app.services.device_service import dispatch_device_task

ORBIT_DEVICE_PERMISSION_SCOPE = "ORBIT_APPLICATION_LAUNCH"
DEVICE_WIDE_APP_ID = "__orbit_device_wide__"

_UNSAFE_SCHEMES = ("javascript:", "data:", "vbscript:", "file:")
_SHELL_METACHAR_RE = re.compile(r"[;|&`$<>\\\r\n\x00]")
_CUSTOM_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]{1,31}:[^\s]*$")
_ANDROID_PKG_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$")

UNIVERSAL_ORBIT_CATALOG: dict[str, dict[str, Any]] = {
    "spotify": {
        "app_id": "spotify",
        "name": "Spotify",
        "aliases": ["spotify music", "music"],
        "category": "Media",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "spotify://",
        "universal_link": "https://open.spotify.com",
        "android_package": "com.spotify.music",
        "android_intent": "intent://open.spotify.com/#Intent;scheme=https;package=com.spotify.music;end",
        "web_fallback": "https://open.spotify.com",
        "desktop_app_key": "spotify",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS PWA uses Universal Links / spotify:// on direct tap, with Spotify Web fallback if the native app is unavailable.",
    },
    "youtube": {
        "app_id": "youtube",
        "name": "YouTube",
        "aliases": ["yt", "youtube app"],
        "category": "Media",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "youtube://",
        "universal_link": "https://www.youtube.com",
        "android_package": "com.google.android.youtube",
        "android_intent": "intent://www.youtube.com/#Intent;scheme=https;package=com.google.android.youtube;end",
        "web_fallback": "https://www.youtube.com",
        "desktop_app_key": "youtube",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens YouTube via Universal Link (https://www.youtube.com) or youtube:// on direct user tap.",
    },
    "instagram": {
        "app_id": "instagram",
        "name": "Instagram",
        "aliases": ["ig", "insta"],
        "category": "Social",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "instagram://app",
        "universal_link": "https://www.instagram.com",
        "android_package": "com.instagram.android",
        "android_intent": "intent://www.instagram.com/#Intent;scheme=https;package=com.instagram.android;end",
        "web_fallback": "https://www.instagram.com",
        "desktop_app_key": "instagram",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Instagram via instagram://app or Universal Link on direct user tap.",
    },
    "tiktok": {
        "app_id": "tiktok",
        "name": "TikTok",
        "aliases": ["tik tok", "musically"],
        "category": "Social",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "snssdk1233://",
        "universal_link": "https://www.tiktok.com",
        "android_package": "com.zhiliaoapp.musically",
        "android_intent": "intent://www.tiktok.com/#Intent;scheme=https;package=com.zhiliaoapp.musically;end",
        "web_fallback": "https://www.tiktok.com",
        "desktop_app_key": "tiktok",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens TikTok via Universal Link (https://www.tiktok.com) or snssdk1233:// on direct tap.",
    },
    "whatsapp": {
        "app_id": "whatsapp",
        "name": "WhatsApp",
        "aliases": ["wa", "whats app"],
        "category": "Communication",
        "platforms": ["ios", "android", "windows", "macos", "web"],
        "ios_scheme": "whatsapp://",
        "universal_link": "https://wa.me/",
        "android_package": "com.whatsapp",
        "android_intent": "intent://send/#Intent;scheme=whatsapp;package=com.whatsapp;end",
        "web_fallback": "https://web.whatsapp.com",
        "desktop_app_key": "whatsapp",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS PWA opens whatsapp:// or wa.me Universal Link on direct user tap.",
    },
    "gmail": {
        "app_id": "gmail",
        "name": "Gmail",
        "aliases": ["google mail", "email", "mail"],
        "category": "Communication",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "googlegmail://",
        "universal_link": "https://mail.google.com/",
        "android_package": "com.google.android.gm",
        "android_intent": "intent://mail.google.com/#Intent;scheme=https;package=com.google.android.gm;end",
        "web_fallback": "https://mail.google.com/",
        "desktop_app_key": "gmail",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS PWA opens googlegmail:// on direct tap or falls back to Gmail Web.",
    },
    "google_calendar": {
        "app_id": "google_calendar",
        "name": "Google Calendar",
        "aliases": ["calendar", "gcal"],
        "category": "Productivity",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "googlecalendar://",
        "universal_link": "https://calendar.google.com/",
        "android_package": "com.google.android.calendar",
        "android_intent": "intent://calendar.google.com/#Intent;scheme=https;package=com.google.android.calendar;end",
        "web_fallback": "https://calendar.google.com/",
        "desktop_app_key": "google_calendar",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS PWA opens googlecalendar:// on direct tap or falls back to Google Calendar Web.",
    },
    "settings": {
        "app_id": "settings",
        "name": "Settings",
        "aliases": ["device settings", "system settings"],
        "category": "System",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "App-Prefs:",
        "universal_link": "",
        "android_package": "com.android.settings",
        "android_intent": "intent:#Intent;action=android.settings.SETTINGS;end",
        "web_fallback": "/settings/preferences",
        "desktop_app_key": "settings",
        "verification_status": "PLATFORM_RESTRICTED",
        "ios_note": "Apple restricts PWAs from opening arbitrary iOS System Settings; ULTRON opens its Settings workspace when iOS blocks App-Prefs:.",
    },
    "browser": {
        "app_id": "browser",
        "name": "Web Browser",
        "aliases": ["my browser", "browser", "safari", "chrome", "google chrome", "edge", "firefox"],
        "category": "System",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "x-web-search://",
        "universal_link": "https://www.google.com",
        "android_package": "com.android.chrome",
        "android_intent": "intent://www.google.com/#Intent;scheme=https;package=com.android.chrome;end",
        "web_fallback": "https://www.google.com",
        "desktop_app_key": "browser",
        "verification_status": "VERIFIED_WEB_HANDOFF",
        "ios_note": "Opens the system default browser via HTTPS handoff or x-web-search://.",
    },
    "camera": {
        "app_id": "camera",
        "name": "Camera",
        "aliases": ["my camera", "camera app"],
        "category": "System",
        "platforms": ["ios", "android", "windows", "macos"],
        "ios_scheme": "",
        "universal_link": "",
        "android_package": "com.android.camera",
        "android_intent": "intent:#Intent;action=android.media.action.IMAGE_CAPTURE;end",
        "web_fallback": "",
        "desktop_app_key": "camera",
        "verification_status": "NATIVE_COMPANION_OR_CAPTURE_REQUIRED",
        "ios_note": "iOS does not expose a public URL scheme to launch the standalone Camera app from a PWA; camera capture requires <input capture> or a native iOS companion.",
    },
    "gallery": {
        "app_id": "gallery",
        "name": "Photos & Gallery",
        "aliases": ["my gallery", "gallery", "photos", "apple photos", "google photos", "photo library"],
        "category": "Media",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "photos-redirect://",
        "universal_link": "https://photos.google.com",
        "android_package": "com.google.android.apps.photos",
        "android_intent": "intent://photos.google.com/#Intent;scheme=https;package=com.google.android.apps.photos;end",
        "web_fallback": "https://photos.google.com",
        "desktop_app_key": "photos",
        "verification_status": "SCHEME_BEST_EFFORT",
        "ios_note": "iOS attempts photos-redirect:// on direct user tap (subject to iOS version restrictions); Android/Web can open Google Photos.",
    },
    "banking": {
        "app_id": "banking",
        "name": "Banking Application",
        "aliases": ["my banking application", "banking application", "banking app", "my bank", "bank", "bank app"],
        "category": "Finance",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "",
        "universal_link": "",
        "android_package": "",
        "android_intent": "",
        "web_fallback": "",
        "desktop_app_key": "banking",
        "verification_status": "MANUAL_REGISTRATION_REQUIRED",
        "ios_note": "Banking apps vary by institution and cannot be enumerated by a PWA. Register your bank's Universal Link or URL scheme in the ORBIT App Library.",
    },
    "telegram": {
        "app_id": "telegram",
        "name": "Telegram",
        "aliases": ["tg"],
        "category": "Communication",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "tg://",
        "universal_link": "https://t.me/",
        "android_package": "org.telegram.messenger",
        "android_intent": "intent://t.me/#Intent;scheme=https;package=org.telegram.messenger;end",
        "web_fallback": "https://web.telegram.org",
        "desktop_app_key": "telegram",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Telegram via tg:// or t.me Universal Link on direct tap.",
    },
    "discord": {
        "app_id": "discord",
        "name": "Discord",
        "aliases": [],
        "category": "Communication",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "discord://",
        "universal_link": "https://discord.com/app",
        "android_package": "com.discord",
        "android_intent": "intent://discord.com/app/#Intent;scheme=https;package=com.discord;end",
        "web_fallback": "https://discord.com/app",
        "desktop_app_key": "discord",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Discord via discord:// or Universal Link.",
    },
    "slack": {
        "app_id": "slack",
        "name": "Slack",
        "aliases": [],
        "category": "Productivity",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "slack://",
        "universal_link": "https://app.slack.com",
        "android_package": "com.slack",
        "android_intent": "intent://app.slack.com/#Intent;scheme=https;package=com.slack;end",
        "web_fallback": "https://app.slack.com",
        "desktop_app_key": "slack",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Slack via slack:// or Universal Link.",
    },
    "zoom": {
        "app_id": "zoom",
        "name": "Zoom",
        "aliases": ["zoom meeting"],
        "category": "Productivity",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "zoomus://",
        "universal_link": "https://zoom.us/join",
        "android_package": "us.zoom.videomeetings",
        "android_intent": "intent://zoom.us/join/#Intent;scheme=https;package=us.zoom.videomeetings;end",
        "web_fallback": "https://zoom.us/join",
        "desktop_app_key": "zoom",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Zoom via zoomus:// or Universal Link.",
    },
    "x_twitter": {
        "app_id": "x_twitter",
        "name": "X (Twitter)",
        "aliases": ["x", "twitter"],
        "category": "Social",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "twitter://",
        "universal_link": "https://x.com",
        "android_package": "com.twitter.android",
        "android_intent": "intent://x.com/#Intent;scheme=https;package=com.twitter.android;end",
        "web_fallback": "https://x.com",
        "desktop_app_key": "x",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens X via twitter:// or https://x.com Universal Link.",
    },
    "netflix": {
        "app_id": "netflix",
        "name": "Netflix",
        "aliases": [],
        "category": "Media",
        "platforms": ["ios", "android", "windows", "macos", "web"],
        "ios_scheme": "nflx://",
        "universal_link": "https://www.netflix.com",
        "android_package": "com.netflix.mediaclient",
        "android_intent": "intent://www.netflix.com/#Intent;scheme=https;package=com.netflix.mediaclient;end",
        "web_fallback": "https://www.netflix.com",
        "desktop_app_key": "netflix",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Netflix via nflx:// or Universal Link.",
    },
    "uber": {
        "app_id": "uber",
        "name": "Uber",
        "aliases": [],
        "category": "Travel",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "uber://",
        "universal_link": "https://m.uber.com",
        "android_package": "com.ubercab",
        "android_intent": "intent://m.uber.com/#Intent;scheme=https;package=com.ubercab;end",
        "web_fallback": "https://m.uber.com",
        "desktop_app_key": "uber",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Uber via uber:// or Universal Link.",
    },
    "maps": {
        "app_id": "maps",
        "name": "Maps",
        "aliases": ["apple maps", "google maps", "navigation"],
        "category": "Navigation",
        "platforms": ["ios", "android", "web"],
        "ios_scheme": "maps://",
        "universal_link": "https://maps.google.com",
        "android_package": "com.google.android.apps.maps",
        "android_intent": "intent://maps.google.com/#Intent;scheme=https;package=com.google.android.apps.maps;end",
        "web_fallback": "https://maps.google.com",
        "desktop_app_key": "maps",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens Apple Maps via maps:// or Google Maps via Universal Link.",
    },
    "messages": {
        "app_id": "messages",
        "name": "Messages",
        "aliases": ["sms", "imessage", "text messages"],
        "category": "Communication",
        "platforms": ["ios", "android", "macos"],
        "ios_scheme": "sms:",
        "universal_link": "",
        "android_package": "com.google.android.apps.messaging",
        "android_intent": "intent:#Intent;scheme=smsto;package=com.google.android.apps.messaging;end",
        "web_fallback": "",
        "desktop_app_key": "messages",
        "verification_status": "VERIFIED_URL_SCHEME",
        "ios_note": "iOS opens Messages via standard sms: URI scheme.",
    },
    "phone": {
        "app_id": "phone",
        "name": "Phone",
        "aliases": ["dialer", "call"],
        "category": "Communication",
        "platforms": ["ios", "android"],
        "ios_scheme": "tel:",
        "universal_link": "",
        "android_package": "com.google.android.dialer",
        "android_intent": "intent:#Intent;action=android.intent.action.DIAL;end",
        "web_fallback": "",
        "desktop_app_key": "phone",
        "verification_status": "VERIFIED_URL_SCHEME",
        "ios_note": "iOS opens Phone via standard tel: URI scheme.",
    },
    "chatgpt": {
        "app_id": "chatgpt",
        "name": "ChatGPT",
        "aliases": ["openai"],
        "category": "Productivity",
        "platforms": ["ios", "android", "macos", "windows", "web"],
        "ios_scheme": "chatgpt://",
        "universal_link": "https://chatgpt.com",
        "android_package": "com.openai.chatgpt",
        "android_intent": "intent://chatgpt.com/#Intent;scheme=https;package=com.openai.chatgpt;end",
        "web_fallback": "https://chatgpt.com",
        "desktop_app_key": "chatgpt",
        "verification_status": "VERIFIED_UNIVERSAL_LINK",
        "ios_note": "iOS opens ChatGPT via chatgpt:// or Universal Link.",
    },
    "vscode": {
        "app_id": "vscode",
        "name": "Visual Studio Code",
        "aliases": ["vs code", "code"],
        "category": "Developer",
        "platforms": ["windows", "macos", "linux", "web"],
        "ios_scheme": "",
        "universal_link": "https://vscode.dev",
        "android_package": "",
        "android_intent": "",
        "web_fallback": "https://vscode.dev",
        "desktop_app_key": "code",
        "verification_status": "DESKTOP_OR_WEB",
        "ios_note": "Desktop launches VS Code via paired desktop agent; browser falls back to vscode.dev.",
    },
}

# Preserve compatibility export for callers/tests referencing SUPPORTED_ORBIT_APPS
SUPPORTED_ORBIT_APPS: dict[str, dict[str, Any]] = UNIVERSAL_ORBIT_CATALOG

_SPOTIFY_URI_RE = re.compile(r"spotify:(playlist|artist|track|album):([A-Za-z0-9]+)")
_SPOTIFY_URL_RE = re.compile(r"open\.spotify\.com/(playlist|artist|track|album)/([A-Za-z0-9]+)")


_ANDROID_INTENT_RE = re.compile(
    r"^intent:(?://)?[^\s`|$<>\\\r\n\x00]*#Intent;(?:[a-zA-Z0-9_.-]+=[^;\s`|$<>\\\r\n\x00]+;)+end$"
)


def validate_launch_target(url: str | None) -> str:
    """Strictly validate a resolved launch URL or URI scheme before returning or dispatching it."""
    raw = (url or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if lower.startswith("intent:"):
        if not _ANDROID_INTENT_RE.match(raw):
            raise ValidationError("Invalid Android intent URI format.")
        return raw
    if _SHELL_METACHAR_RE.search(raw):
        raise ValidationError("Launch target contains disallowed control or shell characters.")
    if lower.startswith(_UNSAFE_SCHEMES):
        raise ValidationError("Launch target uses a disallowed URI scheme.")
    if raw.startswith("/"):
        return raw
    if lower.startswith(("https://", "http://")):
        parsed = urlparse(raw)
        if not parsed.netloc:
            raise ValidationError("HTTP(S) launch target must include a valid host.")
        return raw
    if lower.startswith(("mailto:", "tel:", "sms:", "app-prefs:")):
        return raw
    if _CUSTOM_SCHEME_RE.match(raw):
        return raw
    raise ValidationError("Invalid or unrecognized launch target URI format.")


def _slugify_app_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug[:60] or "custom_app"


def _resolve_spotify_targets(target_uri: str | None) -> tuple[str, str]:
    raw = (target_uri or "").strip()
    if not raw:
        return "spotify://", "https://open.spotify.com"
    m_uri = _SPOTIFY_URI_RE.search(raw)
    if m_uri:
        kind, oid = m_uri.group(1), m_uri.group(2)
        return f"spotify://{kind}/{oid}", f"https://open.spotify.com/{kind}/{oid}"
    m_url = _SPOTIFY_URL_RE.search(raw)
    if m_url:
        kind, oid = m_url.group(1), m_url.group(2)
        return f"spotify://{kind}/{oid}", f"https://open.spotify.com/{kind}/{oid}"
    lower = raw.lower()
    for kind in ("playlist", "artist", "track", "album", "find", "search", "play"):
        if re.search(rf"\b{kind}\b", lower):
            q = re.sub(rf".*\b{kind}\b\s*(?:for\s+)?", "", raw, flags=re.I).strip(" .!?")
            if q:
                return f"spotify://search/{quote(q)}", f"https://open.spotify.com/search/{quote(q)}"
    return "spotify://", "https://open.spotify.com"


def _apply_destination(app_meta: dict[str, Any], target_uri: str | None) -> tuple[str, str, str]:
    """Return (scheme_url, universal_link, web_fallback) enriched safely with optional content/destination."""
    app_id = app_meta["app_id"]
    raw = (target_uri or "").strip()
    scheme = app_meta.get("ios_scheme") or ""
    univ = app_meta.get("universal_link") or ""
    web = app_meta.get("web_fallback") or ""

    if app_id == "spotify":
        s, w = _resolve_spotify_targets(raw)
        return validate_launch_target(s), validate_launch_target(w), validate_launch_target(w)

    if raw:
        if raw.lower().startswith(("https://", "http://")):
            safe_url = validate_launch_target(raw)
            return validate_launch_target(scheme or safe_url), safe_url, safe_url
        q = quote(raw)
        if app_id == "youtube":
            return f"youtube://results?search_query={q}", f"https://www.youtube.com/results?search_query={q}", f"https://www.youtube.com/results?search_query={q}"
        if app_id == "instagram":
            handle = re.sub(r"^@", "", raw).strip()
            if re.match(r"^[A-Za-z0-9._]{1,40}$", handle):
                return f"instagram://user?username={handle}", f"https://www.instagram.com/{handle}/", f"https://www.instagram.com/{handle}/"
        if app_id == "tiktok":
            return validate_launch_target(scheme), f"https://www.tiktok.com/search?q={q}", f"https://www.tiktok.com/search?q={q}"
        if app_id == "maps":
            return f"maps://?q={q}", f"https://maps.google.com/?q={q}", f"https://maps.google.com/?q={q}"

    return validate_launch_target(scheme), validate_launch_target(univ), validate_launch_target(web)


def _serialize_registered_app(r: OrbitRegisteredAppRecord) -> dict[str, Any]:
    return {
        "app_record_id": r.app_record_id,
        "app_id": r.app_id,
        "name": r.name,
        "aliases": json.loads(r.aliases_json or "[]"),
        "category": r.category,
        "platforms": json.loads(r.platforms_json or "[]"),
        "ios_scheme": r.ios_scheme,
        "universal_link": r.universal_link,
        "android_package": r.android_package,
        "android_intent": r.android_intent,
        "desktop_app_key": r.desktop_app_key,
        "web_fallback": r.web_fallback,
        "verification_status": r.verification_status,
        "source": "CUSTOM_REGISTERED",
        "last_launch_at": r.last_launch_at.isoformat() if r.last_launch_at else None,
        "last_launch_status": r.last_launch_status,
        "last_launch_error": r.last_launch_error,
        "ios_note": "Custom registered application. Handoff depends on the installed app claiming the registered URL scheme or Universal Link.",
    }


def _find_app_metadata(
    db: Session,
    *,
    principal: Principal,
    app_id_or_name: str,
) -> tuple[dict[str, Any], OrbitRegisteredAppRecord | None]:
    raw = (app_id_or_name or "").strip()
    if not raw:
        raise ValidationError("app_id or app_name is required.")
    norm = re.sub(r"^(my|the)\s+", "", raw.lower()).strip()
    slug = _slugify_app_id(norm)

    # 1. Check user's custom registered apps first
    custom_rows = db.execute(
        select(OrbitRegisteredAppRecord).where(
            OrbitRegisteredAppRecord.tenant_id == principal.tenant_id,
            OrbitRegisteredAppRecord.user_id == principal.user_id,
        )
    ).scalars().all()
    for cr in custom_rows:
        aliases = [a.lower() for a in json.loads(cr.aliases_json or "[]")]
        if (
            cr.app_id == slug
            or cr.app_id == raw.lower()
            or cr.name.lower() in (norm, raw.lower())
            or norm in aliases
            or raw.lower() in aliases
        ):
            return _serialize_registered_app(cr), cr

    # 2. Check built-in extensible catalog
    if raw.lower() in UNIVERSAL_ORBIT_CATALOG:
        return {**UNIVERSAL_ORBIT_CATALOG[raw.lower()], "source": "BUILTIN_CATALOG"}, None
    if slug in UNIVERSAL_ORBIT_CATALOG:
        return {**UNIVERSAL_ORBIT_CATALOG[slug], "source": "BUILTIN_CATALOG"}, None

    for key, meta in UNIVERSAL_ORBIT_CATALOG.items():
        if meta["name"].lower() == norm:
            return {**meta, "source": "BUILTIN_CATALOG"}, None
        aliases = [a.lower() for a in meta.get("aliases", [])]
        if norm in aliases or raw.lower() in aliases:
            return {**meta, "source": "BUILTIN_CATALOG"}, None

    # 3. Unregistered dynamic app: recognize safely without executing arbitrary commands
    clean_display = re.sub(r"[^A-Za-z0-9 ._+&-]", "", raw).strip()[:80] or "Requested App"
    return {
        "app_id": slug,
        "name": clean_display,
        "aliases": [],
        "category": "Unregistered",
        "platforms": ["ios", "android", "windows", "macos", "linux", "web"],
        "ios_scheme": "",
        "universal_link": "",
        "android_package": "",
        "android_intent": "",
        "web_fallback": "",
        "desktop_app_key": slug,
        "verification_status": "MANUAL_REGISTRATION_REQUIRED",
        "source": "UNREGISTERED",
        "ios_note": (
            f"'{clean_display}' is not yet in the ORBIT registry. "
            "PWAs cannot enumerate arbitrary installed apps on iOS/Android; register its URL scheme, Universal Link, or Android package in ORBIT to enable direct handoff."
        ),
    }, None


def register_custom_app(
    db: Session,
    *,
    principal: Principal,
    name: str,
    aliases: list[str] | None = None,
    category: str = "Custom",
    platforms: list[str] | None = None,
    ios_scheme: str = "",
    universal_link: str = "",
    android_package: str = "",
    desktop_app_key: str = "",
    web_fallback: str = "",
) -> dict[str, Any]:
    clean_name = (name or "").strip()[:120]
    if not clean_name:
        raise ValidationError("Application name is required.")
    app_id = _slugify_app_id(clean_name)

    safe_ios = validate_launch_target(ios_scheme)
    safe_univ = validate_launch_target(universal_link)
    safe_web = validate_launch_target(web_fallback or universal_link)
    clean_pkg = (android_package or "").strip()
    if clean_pkg and not _ANDROID_PKG_RE.match(clean_pkg):
        raise ValidationError("android_package must be a valid reverse-DNS identifier (e.g. com.example.app).")
    android_intent = f"intent://#Intent;package={clean_pkg};end" if clean_pkg else ""

    clean_desktop = re.sub(r"[^a-zA-Z0-9_.-]", "", (desktop_app_key or app_id).strip())[:80]
    clean_aliases = [a.strip()[:80] for a in (aliases or []) if a.strip()]
    clean_platforms = [p.strip().lower() for p in (platforms or ["ios", "android", "windows", "macos", "linux", "web"]) if p.strip()]
    now = datetime.now(timezone.utc)

    rec = db.execute(
        select(OrbitRegisteredAppRecord).where(
            OrbitRegisteredAppRecord.tenant_id == principal.tenant_id,
            OrbitRegisteredAppRecord.user_id == principal.user_id,
            OrbitRegisteredAppRecord.app_id == app_id,
        )
    ).scalar_one_or_none()

    if rec is None:
        rec = OrbitRegisteredAppRecord(
            app_record_id=f"ora_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            app_id=app_id,
            name=clean_name,
            aliases_json=json.dumps(clean_aliases),
            category=(category or "Custom").strip()[:64],
            platforms_json=json.dumps(clean_platforms),
            ios_scheme=safe_ios,
            universal_link=safe_univ,
            android_package=clean_pkg,
            android_intent=android_intent,
            desktop_app_key=clean_desktop,
            web_fallback=safe_web,
            verification_status="MANUAL_REGISTERED",
        )
        db.add(rec)
    else:
        rec.name = clean_name
        rec.aliases_json = json.dumps(clean_aliases)
        rec.category = (category or rec.category).strip()[:64]
        rec.platforms_json = json.dumps(clean_platforms)
        rec.ios_scheme = safe_ios
        rec.universal_link = safe_univ
        rec.android_package = clean_pkg
        rec.android_intent = android_intent
        rec.desktop_app_key = clean_desktop
        rec.web_fallback = safe_web
        rec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_REGISTERED",
        resource=app_id,
        outcome=f"name={clean_name}|has_scheme={bool(safe_ios)}|has_univ={bool(safe_univ)}|has_pkg={bool(clean_pkg)}",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_registered_app(rec)


def delete_custom_app(db: Session, *, principal: Principal, app_id: str) -> dict[str, Any]:
    rec = db.execute(
        select(OrbitRegisteredAppRecord).where(
            OrbitRegisteredAppRecord.tenant_id == principal.tenant_id,
            OrbitRegisteredAppRecord.user_id == principal.user_id,
            OrbitRegisteredAppRecord.app_id == app_id.strip().lower(),
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Custom registered application '{app_id}' not found.")
    db.delete(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_UNREGISTERED",
        resource=rec.app_id,
        outcome="DELETED",
    )
    db.commit()
    return {"status": "DELETED", "app_id": rec.app_id}


def get_device_launch_permission(
    db: Session,
    *,
    principal: Principal,
    device_id: str,
) -> dict[str, Any]:
    clean_dev = (device_id or "this_device").strip() or "this_device"
    rec = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == DEVICE_WIDE_APP_ID,
        )
    ).scalar_one_or_none()
    if rec is None:
        return {
            "permission_id": None,
            "device_id": clean_dev,
            "permission_scope": ORBIT_DEVICE_PERMISSION_SCOPE,
            "status": "NOT_SET",
            "approved_at": None,
            "last_launch_at": None,
            "last_launch_status": None,
        }
    return _serialize_app_perm(rec)


def set_device_launch_permission(
    db: Session,
    *,
    principal: Principal,
    device_id: str,
    device_label: str,
    decision: str,
) -> dict[str, Any]:
    clean_dec = decision.strip().upper()
    if clean_dec not in {"ALWAYS_ALLOW", "DENIED", "REVOKED"}:
        raise ValidationError("decision must be ALWAYS_ALLOW, DENIED, or REVOKED.")
    clean_dev = (device_id or "this_device").strip() or "this_device"
    now = datetime.now(timezone.utc)

    rec = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == DEVICE_WIDE_APP_ID,
        )
    ).scalar_one_or_none()

    if rec is None:
        rec = DeviceAppPermissionRecord(
            permission_id=f"dap_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            device_id=clean_dev,
            device_label=(device_label or "This Device").strip()[:160],
            app_id=DEVICE_WIDE_APP_ID,
            app_name="All Device Applications (ORBIT)",
            status=clean_dec,
            permission_scope=ORBIT_DEVICE_PERMISSION_SCOPE,
            approved_at=now if clean_dec == "ALWAYS_ALLOW" else None,
        )
        db.add(rec)
    else:
        rec.device_label = (device_label or rec.device_label).strip()[:160]
        rec.status = clean_dec
        rec.permission_scope = ORBIT_DEVICE_PERMISSION_SCOPE
        if clean_dec == "ALWAYS_ALLOW":
            rec.approved_at = now
        rec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_DEVICE_LAUNCH_PERMISSION_UPDATED",
        resource=f"{clean_dev}:{ORBIT_DEVICE_PERMISSION_SCOPE}",
        outcome=clean_dec,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_app_perm(rec)


def list_app_permissions(
    db: Session,
    *,
    principal: Principal,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(DeviceAppPermissionRecord).where(
        DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
        DeviceAppPermissionRecord.user_id == principal.user_id,
    )
    if device_id:
        stmt = stmt.where(DeviceAppPermissionRecord.device_id == device_id.strip())
    rows = db.execute(stmt.order_by(DeviceAppPermissionRecord.updated_at.desc())).scalars().all()
    return [_serialize_app_perm(r) for r in rows]


def set_app_permission(
    db: Session,
    *,
    principal: Principal,
    app_id: str,
    device_id: str,
    device_label: str,
    decision: str,
) -> dict[str, Any]:
    clean_dec = decision.strip().upper()
    if clean_dec not in {"ALWAYS_ALLOW", "DENIED", "REVOKED"}:
        raise ValidationError("decision must be ALWAYS_ALLOW, DENIED, or REVOKED.")

    if app_id.strip() == DEVICE_WIDE_APP_ID:
        return set_device_launch_permission(
            db,
            principal=principal,
            device_id=device_id,
            device_label=device_label,
            decision=clean_dec,
        )

    app_meta, _ = _find_app_metadata(db, principal=principal, app_id_or_name=app_id)
    clean_app = app_meta["app_id"]
    clean_dev = device_id.strip() or "this_device"
    now = datetime.now(timezone.utc)

    rec = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == clean_app,
        )
    ).scalar_one_or_none()

    if rec is None:
        rec = DeviceAppPermissionRecord(
            permission_id=f"dap_{uuid.uuid4().hex[:14]}",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            device_id=clean_dev,
            device_label=(device_label or "This Device").strip()[:160],
            app_id=clean_app,
            app_name=app_meta["name"],
            status=clean_dec,
            permission_scope="app_launch",
            approved_at=now if clean_dec == "ALWAYS_ALLOW" else None,
        )
        db.add(rec)
    else:
        rec.device_label = (device_label or rec.device_label).strip()[:160]
        rec.status = clean_dec
        rec.permission_scope = "app_launch"
        if clean_dec == "ALWAYS_ALLOW":
            rec.approved_at = now
        rec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_PERMISSION_UPDATED",
        resource=f"{clean_dev}:{clean_app}",
        outcome=clean_dec,
    )
    db.commit()
    db.refresh(rec)
    return _serialize_app_perm(rec)


def revoke_app_permission(
    db: Session,
    *,
    principal: Principal,
    permission_id: str,
) -> dict[str, Any]:
    rec = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.permission_id == permission_id,
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Application permission '{permission_id}' not found.")
    rec.status = "REVOKED"
    rec.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_PERMISSION_REVOKED",
        resource=f"{rec.device_id}:{rec.app_id}",
        outcome="REVOKED",
    )
    db.commit()
    db.refresh(rec)
    return _serialize_app_perm(rec)


def resolve_universal_app(
    db: Session,
    *,
    principal: Principal,
    query: str,
    platform: str = "ios",
    target_uri: str | None = None,
    preferred_method: str | None = None,
) -> dict[str, Any]:
    app_meta, custom_rec = _find_app_metadata(db, principal=principal, app_id_or_name=query)
    scheme_url, univ_url, web_url = _apply_destination(app_meta, target_uri)
    android_intent = validate_launch_target(app_meta.get("android_intent") or "")
    plat = (platform or "ios").strip().lower()

    available_methods: list[dict[str, Any]] = []
    if univ_url:
        available_methods.append({"method": "universal_link", "label": "Universal Link", "url": univ_url})
    if scheme_url:
        available_methods.append({"method": "url_scheme", "label": "URL Scheme", "url": scheme_url})
    if android_intent:
        available_methods.append({"method": "android_intent", "label": "Android Intent", "url": android_intent})
    if plat in {"windows", "macos", "linux"} and app_meta.get("desktop_app_key"):
        available_methods.append({"method": "desktop_agent", "label": "Paired Desktop Agent", "url": web_url or app_meta["desktop_app_key"]})
    if web_url:
        available_methods.append({"method": "web_fallback", "label": "Browser Fallback", "url": web_url})

    selected_url = scheme_url or univ_url or web_url
    if preferred_method == "universal_link" and univ_url:
        selected_url = univ_url
    elif preferred_method == "web_fallback" and web_url:
        selected_url = web_url
    elif preferred_method == "android_intent" and android_intent:
        selected_url = android_intent
    elif plat == "android" and android_intent:
        selected_url = android_intent

    return {
        "app_id": app_meta["app_id"],
        "app_name": app_meta["name"],
        "category": app_meta.get("category", "Custom"),
        "source": app_meta.get("source", "BUILTIN_CATALOG"),
        "is_registered": app_meta.get("source") != "UNREGISTERED",
        "verification_status": app_meta.get("verification_status", "UNVERIFIED"),
        "platforms": app_meta.get("platforms", []),
        "available_methods": available_methods,
        "launch_url": selected_url,
        "universal_link": univ_url,
        "android_intent_url": android_intent,
        "web_fallback_url": web_url,
        "desktop_app_key": app_meta.get("desktop_app_key") or app_meta["app_id"],
        "platform_limitation_note": app_meta.get("ios_note", ""),
        "custom_record_id": custom_rec.app_record_id if custom_rec else None,
    }


def prepare_or_dispatch_app_launch(
    db: Session,
    *,
    principal: Principal,
    app_id: str,
    device_id: str,
    device_label: str = "This Device",
    platform: str = "ios",
    target_uri: str | None = None,
    allow_once: bool = False,
    preferred_method: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_universal_app(
        db,
        principal=principal,
        query=app_id,
        platform=platform,
        target_uri=target_uri,
        preferred_method=preferred_method,
    )
    clean_app = resolved["app_id"]
    clean_dev = device_id.strip() or "this_device"

    perm = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == clean_app,
        )
    ).scalar_one_or_none()

    device_perm = db.execute(
        select(DeviceAppPermissionRecord).where(
            DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
            DeviceAppPermissionRecord.user_id == principal.user_id,
            DeviceAppPermissionRecord.device_id == clean_dev,
            DeviceAppPermissionRecord.app_id == DEVICE_WIDE_APP_ID,
        )
    ).scalar_one_or_none()

    if perm is not None and perm.status == "DENIED" and not allow_once:
        return {
            "status": "DENIED",
            "app_id": clean_app,
            "app_name": resolved["app_name"],
            "device_id": clean_dev,
            "message": f"Launch permission for {resolved['app_name']} on this device is currently denied.",
        }

    if perm is None and device_perm is not None and device_perm.status == "DENIED" and not allow_once:
        return {
            "status": "DENIED",
            "app_id": clean_app,
            "app_name": resolved["app_name"],
            "device_id": clean_dev,
            "message": f"{ORBIT_DEVICE_PERMISSION_SCOPE} is denied for this device.",
        }

    has_app_always = perm is not None and perm.status == "ALWAYS_ALLOW"
    has_device_always = device_perm is not None and device_perm.status == "ALWAYS_ALLOW"
    has_always_allow = has_app_always or has_device_always

    if not has_always_allow and not allow_once:
        return {
            "status": "APPROVAL_REQUIRED",
            "app_id": clean_app,
            "app_name": resolved["app_name"],
            "device_id": clean_dev,
            "device_label": device_label,
            "permission_scope": ORBIT_DEVICE_PERMISSION_SCOPE,
            "prompt": f"Allow ULTRON to open {resolved['app_name']} (or remember {ORBIT_DEVICE_PERMISSION_SCOPE} for this device)?",
            "actions": ["allow_once", "always_allow_app", "always_allow_device", "deny"],
            "resolution": resolved,
        }

    now = datetime.now(timezone.utc)
    desktop_task = None
    launch_status = "LAUNCH_URL_RESOLVED" if resolved["launch_url"] else "MANUAL_REGISTRATION_REQUIRED"

    if platform.strip().lower() in {"windows", "macos", "linux"}:
        paired = db.execute(
            select(DeviceRecord).where(
                DeviceRecord.device_id == clean_dev,
                DeviceRecord.tenant_id == principal.tenant_id,
                DeviceRecord.status == "ACTIVE",
            )
        ).scalar_one_or_none()
        if paired is not None:
            perms = json.loads(paired.permissions_json or "{}")
            if perms.get("execute_commands"):
                desktop_task = dispatch_device_task(
                    db,
                    principal=principal,
                    device_id=paired.device_id,
                    action="open_application",
                    payload={"app_id": resolved["desktop_app_key"], "target_url": resolved["web_fallback_url"] or resolved["launch_url"]},
                )
                launch_status = "DESKTOP_TASK_QUEUED"

    if perm is not None:
        perm.last_launch_at = now
        perm.last_launch_status = launch_status
        perm.updated_at = now
    if device_perm is not None and has_device_always:
        device_perm.last_launch_at = now
        device_perm.last_launch_status = launch_status
        device_perm.updated_at = now

    if resolved.get("custom_record_id"):
        crec = db.get(OrbitRegisteredAppRecord, resolved["custom_record_id"])
        if crec is not None:
            crec.last_launch_at = now
            crec.last_launch_status = launch_status
            crec.updated_at = now

    perm_mode = "ORBIT_APPLICATION_LAUNCH" if has_device_always else ("ALWAYS_ALLOW" if has_app_always else "ALLOW_ONCE")
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_LAUNCH_DISPATCHED",
        resource=f"{clean_dev}:{clean_app}",
        outcome=f"mode={launch_status}|perm={perm_mode}|registered={resolved['is_registered']}",
    )
    db.commit()

    return {
        "status": "READY_TO_LAUNCH",
        "app_id": clean_app,
        "app_name": resolved["app_name"],
        "device_id": clean_dev,
        "permission_mode": perm_mode,
        "launch_status": launch_status,
        "launch_url": resolved["launch_url"],
        "universal_link": resolved["universal_link"],
        "android_intent_url": resolved["android_intent_url"],
        "web_fallback_url": resolved["web_fallback_url"],
        "available_methods": resolved["available_methods"],
        "is_registered": resolved["is_registered"],
        "verification_status": resolved["verification_status"],
        "desktop_task": desktop_task,
        "platform_limitation_note": resolved["platform_limitation_note"],
        "app_recognised": True,
        "launch_url_resolved": bool(resolved["launch_url"]),
        "handoff_attempted": bool(desktop_task),
        "os_confirmed": False,
    }


def list_orbit_app_library(
    db: Session,
    *,
    principal: Principal,
    device_id: str | None = None,
) -> dict[str, Any]:
    clean_dev = (device_id or "this_device").strip() or "this_device"
    perms = list_app_permissions(db, principal=principal, device_id=clean_dev)
    perm_by_app = {p["app_id"]: p for p in perms}
    device_perm = get_device_launch_permission(db, principal=principal, device_id=clean_dev)

    custom_rows = db.execute(
        select(OrbitRegisteredAppRecord).where(
            OrbitRegisteredAppRecord.tenant_id == principal.tenant_id,
            OrbitRegisteredAppRecord.user_id == principal.user_id,
        ).order_by(OrbitRegisteredAppRecord.name.asc())
    ).scalars().all()

    items: dict[str, dict[str, Any]] = {}
    for key, meta in UNIVERSAL_ORBIT_CATALOG.items():
        p = perm_by_app.get(key)
        items[key] = {
            **meta,
            "source": "BUILTIN_CATALOG",
            "permission": p,
            "last_launch_at": p["last_launch_at"] if p else None,
            "last_launch_status": p["last_launch_status"] if p else None,
            "last_launch_error": None,
        }

    for cr in custom_rows:
        ser = _serialize_registered_app(cr)
        p = perm_by_app.get(cr.app_id)
        items[cr.app_id] = {
            **ser,
            "permission": p,
            "last_launch_at": ser["last_launch_at"] or (p["last_launch_at"] if p else None),
            "last_launch_status": ser["last_launch_status"] or (p["last_launch_status"] if p else None),
        }

    return {
        "total": len(items),
        "device_id": clean_dev,
        "device_permission": device_perm,
        "apps": list(items.values()),
    }


def get_platform_discovery_report(
    db: Session,
    *,
    principal: Principal,
    platform: str = "ios",
    device_id: str = "this_device",
) -> dict[str, Any]:
    plat = (platform or "ios").strip().lower()
    paired = db.execute(
        select(DeviceRecord).where(
            DeviceRecord.device_id == device_id,
            DeviceRecord.tenant_id == principal.tenant_id,
            DeviceRecord.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    desktop_authorized = False
    if paired is not None:
        desktop_authorized = bool(json.loads(paired.permissions_json or "{}").get("execute_commands"))

    return {
        "platform": plat,
        "device_id": device_id,
        "desktop_agent_paired": paired is not None,
        "desktop_agent_authorized": desktop_authorized,
        "capabilities": {
            "ios": {
                "automatic_app_enumeration": False,
                "supported_methods": ["Universal Links (HTTPS)", "Known URL Schemes", "Manual App Registration"],
                "native_companion_required_for": [
                    "Enumerating arbitrary installed apps",
                    "Confirming whether iOS successfully opened a third-party app",
                    "Opening Camera/Settings directly without Safari/PWA prompt",
                ],
            },
            "android": {
                "automatic_app_enumeration": False,
                "supported_methods": ["Android Intent URIs (package=...)", "App Links (HTTPS)", "Manual Package Registration"],
                "native_companion_required_for": [
                    "Querying installed packages (subject to Android 11+ <queries> visibility)",
                    "Independent launch confirmation from the OS",
                ],
            },
            "desktop": {
                "automatic_app_enumeration": desktop_authorized,
                "supported_methods": ["Paired ULTRON Desktop Agent (with execute_commands)", "Web Fallback", "Manual Registration"],
                "native_companion_required_for": [
                    "Discovering locally installed desktop applications",
                    "Launching native executables with OS exit-code confirmation",
                ],
            },
        },
    }


def _serialize_app_perm(r: DeviceAppPermissionRecord) -> dict[str, Any]:
    return {
        "permission_id": r.permission_id,
        "user_id": r.user_id,
        "device_id": r.device_id,
        "device_label": r.device_label,
        "app_id": r.app_id,
        "app_name": r.app_name,
        "status": r.status,
        "permission_scope": r.permission_scope,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "last_launch_at": r.last_launch_at.isoformat() if r.last_launch_at else None,
        "last_launch_status": r.last_launch_status,
        "updated_at": r.updated_at.isoformat(),
    }


_VALID_HANDOFF_OUTCOMES = {
    "HANDOFF_TAPPED",
    "HANDOFF_PAGE_HIDDEN",
    "HANDOFF_NO_APP_SWITCH_TIMEOUT",
    "WEB_FALLBACK_OPENED",
    "LAUNCH_FAILED",
}


def record_handoff_outcome(
    db: Session,
    *,
    principal: Principal,
    app_id: str,
    device_id: str,
    outcome: str,
    detail: str = "",
) -> dict[str, Any]:
    clean_outcome = outcome.strip().upper()
    if clean_outcome not in _VALID_HANDOFF_OUTCOMES:
        raise ValidationError(f"Invalid handoff outcome '{outcome}'.")
    clean_app = _slugify_app_id(app_id)
    clean_dev = (device_id or "this_device").strip() or "this_device"
    now = datetime.now(timezone.utc)

    for target_app in (clean_app, DEVICE_WIDE_APP_ID):
        perm = db.execute(
            select(DeviceAppPermissionRecord).where(
                DeviceAppPermissionRecord.tenant_id == principal.tenant_id,
                DeviceAppPermissionRecord.user_id == principal.user_id,
                DeviceAppPermissionRecord.device_id == clean_dev,
                DeviceAppPermissionRecord.app_id == target_app,
            )
        ).scalar_one_or_none()
        if perm is not None:
            perm.last_launch_at = now
            perm.last_launch_status = clean_outcome
            perm.updated_at = now

    crec = db.execute(
        select(OrbitRegisteredAppRecord).where(
            OrbitRegisteredAppRecord.tenant_id == principal.tenant_id,
            OrbitRegisteredAppRecord.user_id == principal.user_id,
            OrbitRegisteredAppRecord.app_id == clean_app,
        )
    ).scalar_one_or_none()
    if crec is not None:
        crec.last_launch_at = now
        crec.last_launch_status = clean_outcome
        crec.last_launch_error = (detail or "")[:500] if clean_outcome in {"HANDOFF_NO_APP_SWITCH_TIMEOUT", "LAUNCH_FAILED"} else None
        crec.updated_at = now

    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="ORBIT_APP_HANDOFF_REPORTED",
        resource=f"{clean_dev}:{clean_app}",
        outcome=f"{clean_outcome}|{(detail or '')[:160]}",
    )
    db.commit()
    return {
        "app_id": clean_app,
        "device_id": clean_dev,
        "handoff_status": clean_outcome,
        "os_confirmed": False,
        "recorded_at": now.isoformat(),
    }

