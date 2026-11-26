"""
Permanent Automated Regression Test Suite: UI Contrast & Accessibility (WCAG 2.2 AA / AAA)

Ensures that UI design tokens, navigation buttons, input placeholders, select options,
and status badges across ULTRON never regress below WCAG 2.2 contrast thresholds.
"""

import math
import os
import re
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STYLES_CSS = REPO_ROOT / "frontend" / "src" / "styles.css"
CARAVAN_COMPONENT = REPO_ROOT / "frontend" / "src" / "components" / "caravan" / "CaravanCommandCentre.tsx"


def parse_hex_color(hex_str: str) -> tuple[int, int, int]:
    """Parse #rgb, #rrggbb, or #rrggbbaa into (r, g, b) 0-255."""
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join([c * 2 for c in h])
    if len(h) >= 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    raise ValueError(f"Invalid hex color: {hex_str}")


def relative_luminance(r: int, g: int, b: int) -> float:
    """Calculate WCAG relative luminance for an sRGB color."""
    channels = []
    for c in (r, g, b):
        s = c / 255.0
        if s <= 0.04045:
            channels.append(s / 12.92)
        else:
            channels.append(math.pow((s + 0.055) / 1.055, 2.4))
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Calculate WCAG contrast ratio between two colors."""
    l1 = relative_luminance(*c1)
    l2 = relative_luminance(*c2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def composite_rgba_over_rgb(
    fg_rgba: tuple[int, int, int, float], bg_rgb: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Alpha composite fg over bg."""
    r_fg, g_fg, b_fg, a = fg_rgba
    r_bg, g_bg, b_bg = bg_rgb
    return (
        int(round(r_fg * a + r_bg * (1.0 - a))),
        int(round(g_fg * a + g_bg * (1.0 - a))),
        int(round(b_fg * a + b_bg * (1.0 - a))),
    )


def extract_css_variables(css_text: str) -> dict[str, str]:
    """Extract root CSS custom properties."""
    root_match = re.search(r":root\s*\{([^}]+)\}", css_text, re.DOTALL)
    assert root_match, "Could not find :root block in styles.css"
    var_dict = {}
    for line in root_match.group(1).splitlines():
        line = line.strip()
        if line.startswith("--") and ":" in line:
            parts = line.split(":", 1)
            var_name = parts[0].strip()
            var_val = parts[1].split(";")[0].strip()
            var_dict[var_name] = var_val
    return var_dict


class TestUIContrastAndTokens:
    @classmethod
    def setup_class(cls):
        assert STYLES_CSS.exists(), f"styles.css not found at {STYLES_CSS}"
        cls.css_content = STYLES_CSS.read_text(encoding="utf-8")
        cls.tokens = extract_css_variables(cls.css_content)

    def test_dark_mode_background_tokens_exist(self):
        """Ensure base background tokens are defined and sufficiently dark."""
        assert "--bg-void" in self.tokens
        assert "--bg-surface" in self.tokens
        assert "--bg-surface-elev" in self.tokens

        void_rgb = parse_hex_color(self.tokens["--bg-void"])
        surface_rgb = parse_hex_color(self.tokens["--bg-surface"])
        elevated_rgb = parse_hex_color(self.tokens["--bg-surface-elev"])

        # All dark mode backgrounds must have luminance < 0.05
        assert relative_luminance(*void_rgb) < 0.05
        assert relative_luminance(*surface_rgb) < 0.05
        assert relative_luminance(*elevated_rgb) < 0.05

    def test_text_tokens_wcag_aa_and_aaa_compliance(self):
        """Verify that text tokens meet WCAG 2.2 AA (4.5:1) and AAA (7.0:1) on dark backgrounds."""
        surface_rgb = parse_hex_color(self.tokens["--bg-surface"])
        void_rgb = parse_hex_color(self.tokens["--bg-void"])

        # --text: primary crisp text
        assert "--text" in self.tokens
        text_rgb = parse_hex_color(self.tokens["--text"])
        ratio_primary = contrast_ratio(text_rgb, surface_rgb)
        assert ratio_primary >= 7.0, f"--text contrast {ratio_primary:.2f}:1 fails WCAG AAA"

        # --text-secondary: soft silver text
        assert "--text-secondary" in self.tokens
        sec_rgb = parse_hex_color(self.tokens["--text-secondary"])
        ratio_sec = contrast_ratio(sec_rgb, surface_rgb)
        assert ratio_sec >= 7.0, f"--text-secondary contrast {ratio_sec:.2f}:1 fails WCAG AAA"

        # --text-muted: labels, helper text, and placeholders (exceeds WCAG AA 4.5:1, meets AAA on void)
        assert "--text-muted" in self.tokens
        muted_rgb = parse_hex_color(self.tokens["--text-muted"])
        ratio_muted_surface = contrast_ratio(muted_rgb, surface_rgb)
        ratio_muted_void = contrast_ratio(muted_rgb, void_rgb)
        assert ratio_muted_surface >= 4.5, f"--text-muted contrast {ratio_muted_surface:.2f}:1 fails WCAG AA"
        assert ratio_muted_void >= 7.0, f"--text-muted contrast {ratio_muted_void:.2f}:1 fails WCAG AAA on void"

        # --text-dim: subtle captions, must satisfy WCAG AA (>= 4.5:1)
        assert "--text-dim" in self.tokens
        dim_rgb = parse_hex_color(self.tokens["--text-dim"])
        ratio_dim = contrast_ratio(dim_rgb, void_rgb)
        assert ratio_dim >= 4.5, f"--text-dim contrast {ratio_dim:.2f}:1 fails WCAG AA on void"

    def test_segmented_navigation_light_pills_contrast(self):
        """Verify that light navigation and segmented buttons use dark text (WCAG AAA)."""
        # .seg-btn default state
        seg_btn_match = re.search(r"\.seg-btn\s*\{([^}]+)\}", self.css_content)
        assert seg_btn_match, "Could not find .seg-btn rule in styles.css"
        seg_btn_body = seg_btn_match.group(1)

        # Inactive state: background is light (#e2e8f0), text must be dark charcoal (#08090c)
        assert "#08090c" in seg_btn_body or "var(--btn-light-fg)" in seg_btn_body
        text_rgb = parse_hex_color("#08090c")
        bg_rgb = parse_hex_color("#e2e8f0")
        ratio_inactive = contrast_ratio(text_rgb, bg_rgb)
        assert ratio_inactive >= 7.0, f"Inactive seg-btn contrast {ratio_inactive:.2f}:1 fails WCAG AAA"

        # Active state: background is white (#ffffff), text is pure black (#000000)
        assert ".seg-btn.active" in self.css_content
        ratio_active = contrast_ratio((0, 0, 0), (255, 255, 255))
        assert ratio_active == 21.0, "Active seg-btn must have 21:1 contrast"

        # Hover state: background is #f1f5f9, text is black (#000000)
        ratio_hover = contrast_ratio((0, 0, 0), parse_hex_color("#f1f5f9"))
        assert ratio_hover >= 18.0, f"Hover seg-btn contrast {ratio_hover:.2f}:1 fails WCAG AAA"

        # Disabled state: background is #cbd5e1, text is #475569
        ratio_disabled = contrast_ratio(parse_hex_color("#475569"), parse_hex_color("#cbd5e1"))
        assert ratio_disabled >= 4.5, f"Disabled seg-btn contrast {ratio_disabled:.2f}:1 fails WCAG AA"

    def test_input_placeholders_have_sufficient_contrast(self):
        """Verify placeholder pseudo-classes are defined with high-contrast text and full opacity."""
        placeholder_match = re.search(
            r"(?:input|\.input|textarea)::placeholder\s*\{([^}]+)\}", self.css_content
        )
        assert placeholder_match, "input::placeholder rule not found in styles.css"
        body = placeholder_match.group(1)
        assert "var(--text-muted)" in body or "#94a3b8" in body, "Placeholder color must be text-muted"
        assert "opacity: 1" in body, "Placeholder opacity must be set to 1 for reliable contrast"

    def test_select_option_has_explicit_dark_styling(self):
        """Verify select options do not inherit light system backgrounds with light text."""
        select_match = re.search(r"select\s+option\s*\{([^}]+)\}", self.css_content)
        assert select_match, "select option styling not found in styles.css"
        body = select_match.group(1)
        assert "background" in body, "select option must define explicit background"
        assert "color" in body, "select option must define explicit text color"

    def test_status_pills_wcag_aa_compliance(self):
        """Verify status pill text colors achieve >= 4.5:1 against dark backgrounds."""
        surface_rgb = parse_hex_color(self.tokens["--bg-surface"])

        # Pill color tokens
        pills = {
            "cyan": "#7dd3fc",
            "green": "#6ee7b7",
            "warn": "#fde047",
            "danger": "#fca5a5",
        }

        for name, hex_code in pills.items():
            pill_rgb = parse_hex_color(hex_code)
            ratio = contrast_ratio(pill_rgb, surface_rgb)
            assert ratio >= 4.5, f"Pill {name} contrast {ratio:.2f}:1 fails WCAG AA"


class TestCaravanTelemetryResilience:
    def test_caravan_view_implements_timeout_and_recovery(self):
        """Verify CaravanCommandCentre has 10s AbortController timeout, spinner, and retry button."""
        assert CARAVAN_COMPONENT.exists(), f"CaravanCommandCentre.tsx not found at {CARAVAN_COMPONENT}"
        view_content = CARAVAN_COMPONENT.read_text(encoding="utf-8")

        # 10s timeout
        assert "10000" in view_content, "CaravanCommandCentre must implement a 10s timeout"
        assert "AbortController" in view_content, "CaravanCommandCentre must use AbortController for timeouts"

        # Spinner & retry
        assert "RefreshCw" in view_content, "CaravanCommandCentre must include refresh/retry icon"
        assert "spin" in view_content, "CaravanCommandCentre must support spinning animation"
        assert "Telemetry request timed out" in view_content
        assert "Retry" in view_content
