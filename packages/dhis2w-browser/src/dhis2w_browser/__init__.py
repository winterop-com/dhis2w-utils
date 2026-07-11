"""Playwright-based helpers for DHIS2 UI automation."""

from dhis2w_browser.dashboard import (
    CaptureResult,
    DashboardTarget,
    add_banner,
    capture_dashboard,
    slugify,
    switch_dashboard,
    trim_background,
)
from dhis2w_browser.maps import (
    MapCaptureResult,
    MapTarget,
    add_map_banner,
    capture_map,
    slugify_map,
)
from dhis2w_browser.oauth2 import OAuth2LoginResult, drive_login_form, drive_oauth2_login
from dhis2w_browser.pat import PatAttribute, PatOptions, PatPayload, create_pat
from dhis2w_browser.session import (
    CookiePair,
    logged_in_page,
    parse_cookie_header,
    resolve_headless,
    session_from_cookie,
    session_from_cookie_header,
)
from dhis2w_browser.visualization import (
    VisualizationCaptureResult,
    VisualizationTarget,
    add_viz_banner,
    capture_visualization,
    slugify_viz,
)

__all__ = [
    "CaptureResult",
    "CookiePair",
    "DashboardTarget",
    "MapCaptureResult",
    "MapTarget",
    "OAuth2LoginResult",
    "PatAttribute",
    "PatOptions",
    "PatPayload",
    "VisualizationCaptureResult",
    "VisualizationTarget",
    "add_banner",
    "add_map_banner",
    "add_viz_banner",
    "capture_dashboard",
    "capture_map",
    "capture_visualization",
    "create_pat",
    "drive_login_form",
    "drive_oauth2_login",
    "logged_in_page",
    "parse_cookie_header",
    "resolve_headless",
    "session_from_cookie",
    "session_from_cookie_header",
    "slugify",
    "slugify_map",
    "slugify_viz",
    "switch_dashboard",
    "trim_background",
]
