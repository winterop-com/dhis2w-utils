"""Service layer for the `browser` plugin — thin wrappers around `dhis2w_browser`.

Imports from `dhis2w-browser` (the Playwright-carrying workspace member) are
guarded so the plugin stays importable even when the optional `[browser]`
extra isn't installed. The CLI surface substitutes a stub command in that
case; every real call funnels through `require_browser()` here and raises
a clear error if the module is missing.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from dhis2w_client.v41 import BasicAuth

from dhis2w_core.profile import Profile
from dhis2w_core.v41.client_context import open_client

if TYPE_CHECKING:
    from dhis2w_browser import CaptureResult, MapCaptureResult, PatOptions, VisualizationCaptureResult
    from playwright.async_api import BrowserContext, Page


class BrowserExtraNotInstalled(RuntimeError):
    """Raised when a `browser` command runs without the `[browser]` extra."""


class BrowserWorkflowNotSupported(RuntimeError):
    """Raised when a profile's auth type can't drive a Playwright session.

    PAT profiles hit this: DHIS2 PATs are stateless and never mint a
    `JSESSIONID`, so there's no cookie to inject into the browser. The
    workaround is to use a Basic (or OIDC, once wired) profile for
    browser-driven workflows.
    """


def require_browser() -> None:
    """Confirm `dhis2w_browser` is importable; otherwise raise an install hint."""
    if find_spec("dhis2w_browser") is None:
        raise BrowserExtraNotInstalled(
            "The `d2w browser` commands need the Playwright extra. "
            "Install with `uv add 'dhis2w-cli[browser]'` "
            "(or `uv add dhis2w-browser`), then run "
            "`playwright install chromium` once to pull the driver.",
        )


async def create_pat(
    url: str,
    username: str,
    password: str,
    *,
    options: PatOptions | None = None,
    headless: bool | None = None,
) -> str:
    """Mint a DHIS2 Personal Access Token V2 via an authenticated browser session."""
    require_browser()
    from dhis2w_browser import create_pat as _create_pat  # noqa: PLC0415 — optional-extra guard

    return await _create_pat(url, username, password, options=options, headless=headless)


async def mint_jsessionid(profile: Profile) -> str:
    """Hit `GET /api/me` with the profile's credentials; return the minted JSESSIONID.

    Basic profiles produce a session cookie in the response `Set-Cookie`
    header on any authenticated request. PAT and OAuth2 profiles raise
    `BrowserWorkflowNotSupported` — PATs are stateless in DHIS2, and the
    OAuth2 Bearer-token-to-JSESSIONID exchange has not been wired (needs
    a smoke test to confirm DHIS2 mints a JSESSIONID when
    `Authorization: Bearer` is presented to `/api/me`). Session profiles
    never reach here — `authenticated_session` injects their stored cookie
    directly rather than minting one.
    """
    if profile.auth == "session":
        raise BrowserWorkflowNotSupported(
            "Session profiles carry their session cookie in `profile.cookie` and inject it "
            "directly — there is no JSESSIONID to mint. Drive browser workflows through "
            "`authenticated_session`, which reads the stored cookie.",
        )
    if profile.auth == "pat":
        raise BrowserWorkflowNotSupported(
            "PAT profiles cannot drive browser workflows — DHIS2 PATs are stateless "
            "and do not mint a JSESSIONID cookie. Use a Basic profile (username + "
            "password) for dashboard screenshots, maintenance-app driving, and "
            "other Playwright-based flows.",
        )
    if profile.auth == "oauth2":
        raise BrowserWorkflowNotSupported(
            "OAuth2 / OIDC profiles cannot drive browser workflows yet — the "
            "Bearer-token-to-JSESSIONID exchange has not been wired. Use a Basic "
            "profile (username + password) for dashboard screenshots, "
            "maintenance-app driving, and other Playwright-based flows.",
        )
    if profile.username is None or profile.password is None:
        raise BrowserWorkflowNotSupported(
            f"Profile auth={profile.auth!r} has no username/password; cannot mint a JSESSIONID without credentials.",
        )
    auth = BasicAuth(username=profile.username, password=profile.password)
    async with httpx.AsyncClient(base_url=profile.base_url.rstrip("/")) as http_client:
        response = await http_client.get("/api/me", headers=await auth.headers())
        response.raise_for_status()
        jsessionid = response.cookies.get("JSESSIONID")
        if not jsessionid:
            raise RuntimeError(
                "DHIS2 did not return a JSESSIONID cookie on /api/me. Check that "
                "Basic auth is enabled on this instance.",
            )
        return jsessionid


@asynccontextmanager
async def authenticated_session(
    profile: Profile,
    *,
    headless: bool | None = None,
    navigate_to: str | None = None,
) -> AsyncGenerator[tuple[BrowserContext, Page]]:
    """Yield a Playwright `(context, page)` authenticated as the profile's user.

    Session profiles inject their stored `profile.cookie` directly (no login
    dance). Basic profiles mint a `JSESSIONID` from their credentials (via
    `mint_jsessionid`) and inject it. Either way a fresh browser context is
    seeded with the session cookie — no React login form interaction required.
    Raises `BrowserWorkflowNotSupported` for auth types that can't produce a
    session (PAT, OAuth2) or a session profile that has no cookie.
    """
    require_browser()

    if profile.auth == "session":
        from dhis2w_browser import session_from_cookie_header  # noqa: PLC0415 — optional-extra guard

        if not profile.cookie:
            raise BrowserWorkflowNotSupported(
                "Profile auth='session' has no session cookie; there is no session material to inject. "
                "Re-run `d2w profile add <name> --auth session` with the Cookie header captured from an "
                "authenticated browser (e.g. `JSESSIONID=...`).",
            )
        async with session_from_cookie_header(
            profile.base_url,
            profile.cookie,
            headless=headless,
            navigate_to=navigate_to,
        ) as (context, page):
            yield context, page
        return

    from dhis2w_browser import session_from_cookie  # noqa: PLC0415 — optional-extra guard

    jsessionid = await mint_jsessionid(profile)
    async with session_from_cookie(
        profile.base_url,
        jsessionid,
        headless=headless,
        navigate_to=navigate_to,
    ) as (context, page):
        yield context, page


async def resolve_banner_username(profile: Profile) -> str:
    """Return a display username for capture banners, resolving session profiles via `GET /api/me`.

    Basic profiles carry `profile.username` directly. Session profiles have no
    username field, so the live session (its stored cookie) is asked `/api/me`
    for one; if the server doesn't surface a username, the auth kind stands in.
    """
    if profile.username is not None:
        return profile.username
    async with open_client(profile) as client:
        raw = await client.get_raw("/api/me", params={"fields": "username"})
    username = raw.get("username")
    return username if isinstance(username, str) else profile.auth


async def list_dashboards(profile: Profile) -> list[dict[str, object]]:
    """List every dashboard on the instance — (uid, display name, item count) triples.

    Returns the raw-ish shape `GET /api/dashboards` ships so the caller can
    filter freely before kicking off the (expensive) screenshot loop.
    """
    async with open_client(profile) as client:
        raw = await client.get_raw(
            "/api/dashboards",
            params={"fields": "id,displayName,dashboardItems[id]", "paging": "false"},
        )
    dashboards = raw.get("dashboards")
    if not isinstance(dashboards, list):
        return []
    return [entry for entry in dashboards if isinstance(entry, dict)]


def instance_slug(base_url: str) -> str:
    """Filesystem-safe slug for a DHIS2 base URL.

    Strips the scheme, replaces `/` and `:` with `-`, collapses trailing
    separators. Used to namespace captures per instance so multi-stack
    runs don't overwrite each other: `https://play.dhis2.org/40` →
    `play.dhis2.org-40`, `http://localhost:8080` → `localhost-8080`.
    """
    import re  # noqa: PLC0415 — tight local scope

    stripped = re.sub(r"^https?://", "", base_url).rstrip("/")
    return re.sub(r"[/:]+", "-", stripped) or "instance"


async def capture_dashboards(
    profile: Profile,
    *,
    output_dir: Path,
    only: Sequence[str] | None = None,
    headless: bool | None = None,
    banner: bool = True,
    trim: bool = True,
) -> list[CaptureResult]:
    """Capture full-page PNGs of every (or `only=...`) dashboard for the profile.

    Output PNGs land under
    `{output_dir}/{instance-slug}/{YYYY-MM-DD}-{dashboard-slug}.png` — the
    instance-slug namespace keeps multi-stack runs from overwriting each
    other. Each capture shares the same Playwright context (one login,
    one dashboard-app load) and swaps dashboards via hash navigation, so
    the total wall-clock time scales as O(dashboards) not O(logins).
    """
    require_browser()
    from datetime import UTC, datetime  # noqa: PLC0415 — optional-extra guard

    from dhis2w_browser import (  # noqa: PLC0415 — optional-extra guard
        DashboardTarget,
        add_banner,
        capture_dashboard,
        slugify,
        switch_dashboard,
        trim_background,
    )

    banner_username = await resolve_banner_username(profile)

    instance_dir = output_dir / instance_slug(profile.base_url)
    instance_dir.mkdir(parents=True, exist_ok=True)
    dashboards_raw = await list_dashboards(profile)
    targets: list[DashboardTarget] = []
    for entry in dashboards_raw:
        uid = entry.get("id")
        if not isinstance(uid, str):
            continue
        if only is not None and uid not in only:
            continue
        display_name = entry.get("displayName")
        items = entry.get("dashboardItems")
        item_count = len(items) if isinstance(items, list) else 0
        targets.append(
            DashboardTarget(
                uid=uid,
                display_name=str(display_name) if isinstance(display_name, str) else uid,
                item_count=item_count,
            )
        )

    if not targets:
        return []

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    results: list[CaptureResult] = []
    # Land directly in the dashboard app so the first capture doesn't pay for
    # app-shell initialisation on the way in.
    async with authenticated_session(
        profile,
        headless=headless,
        navigate_to="/dhis-web-dashboard/",
    ) as (_, page):
        for target in targets:
            output_path = instance_dir / f"{today}-{slugify(target.display_name)}.png"
            await switch_dashboard(page, target.uid)
            result = await capture_dashboard(page, target, output_path)
            if trim:
                trim_background(output_path)
            if banner:
                add_banner(
                    output_path,
                    target.display_name,
                    instance_url=profile.base_url,
                    username=banner_username,
                    item_count=target.item_count,
                )
            results.append(result)
    return results


async def list_maps_for_screenshot(profile: Profile) -> list[dict[str, object]]:
    """Fetch every Map's uid + display name + layer count for the screenshot loop."""
    async with open_client(profile) as client:
        raw = await client.get_raw(
            "/api/maps",
            params={"fields": "id,name,displayName,mapViews[id]", "paging": "false"},
        )
    maps = raw.get("maps")
    if not isinstance(maps, list):
        return []
    return [entry for entry in maps if isinstance(entry, dict)]


async def capture_maps(
    profile: Profile,
    *,
    output_dir: Path,
    only: Sequence[str] | None = None,
    headless: bool | None = None,
    banner: bool = True,
    trim: bool = True,
) -> list[MapCaptureResult]:
    """Capture a PNG for each Map UID (or every map when `only` is None).

    Shared Playwright context across the batch — one login, one app-shell
    load, hash-only navigation between maps via
    `iframe.contentWindow.location.hash = '/{uid}'`.
    """
    require_browser()
    from datetime import UTC, datetime  # noqa: PLC0415

    from dhis2w_browser import (  # noqa: PLC0415
        MapTarget,
        add_map_banner,
        capture_map,
        slugify_map,
        trim_background,
    )

    banner_username = await resolve_banner_username(profile)

    instance_dir = output_dir / instance_slug(profile.base_url)
    instance_dir.mkdir(parents=True, exist_ok=True)
    maps_raw = await list_maps_for_screenshot(profile)
    targets: list[tuple[MapTarget, int]] = []
    for entry in maps_raw:
        uid = entry.get("id")
        if not isinstance(uid, str):
            continue
        if only is not None and uid not in only:
            continue
        display = entry.get("displayName") or entry.get("name") or uid
        views = entry.get("mapViews")
        layer_count = len(views) if isinstance(views, list) else 0
        targets.append(
            (
                MapTarget(
                    uid=uid,
                    display_name=str(display) if isinstance(display, str) else uid,
                ),
                layer_count,
            ),
        )

    if not targets:
        return []

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    results: list[MapCaptureResult] = []
    first_target, _ = targets[0]
    async with authenticated_session(
        profile,
        headless=headless,
        navigate_to=f"/dhis-web-maps/#/{first_target.uid}",
    ) as (_, page):
        for index, (target, layer_count) in enumerate(targets):
            if index > 0:
                await page.evaluate(
                    f"""() => {{
                        const iframe = document.querySelector('iframe');
                        if (iframe && iframe.contentWindow) {{
                            iframe.contentWindow.location.hash = '/{target.uid}';
                        }}
                    }}""",
                )
                import asyncio as _asyncio  # noqa: PLC0415

                await _asyncio.sleep(2)
            output_path = instance_dir / f"{today}-{slugify_map(target.display_name)}.png"
            result = await capture_map(page, target, output_path)
            if trim:
                trim_background(output_path)
            if banner:
                add_map_banner(
                    output_path,
                    target.display_name,
                    instance_url=profile.base_url,
                    username=banner_username,
                    layer_count=layer_count,
                )
            results.append(result)
    return results


async def list_visualizations_for_screenshot(profile: Profile) -> list[dict[str, object]]:
    """Fetch every Visualization's uid / name / type for the screenshot loop."""
    async with open_client(profile) as client:
        raw = await client.get_raw(
            "/api/visualizations",
            params={"fields": "id,name,displayName,type", "paging": "false"},
        )
    vizes = raw.get("visualizations")
    if not isinstance(vizes, list):
        return []
    return [entry for entry in vizes if isinstance(entry, dict)]


async def capture_visualizations(
    profile: Profile,
    *,
    output_dir: Path,
    only: Sequence[str] | None = None,
    headless: bool | None = None,
    banner: bool = True,
    trim: bool = True,
) -> list[VisualizationCaptureResult]:
    """Capture a PNG for each Visualization UID (or every viz when `only` is None).

    Output PNGs land under `{output_dir}/{instance-slug}/{YYYY-MM-DD}-{viz-slug}.png`
    — same instance-namespacing scheme as dashboard captures. Each capture
    shares a single authenticated Playwright context and navigates the
    inner iframe via hash routing (`/apps/data-visualizer#/<uid>`) so the
    total wall-clock scales linearly with viz count, not with login count.
    """
    require_browser()
    from datetime import UTC, datetime  # noqa: PLC0415 — optional-extra guard

    from dhis2w_browser import (  # noqa: PLC0415 — optional-extra guard
        VisualizationTarget,
        add_viz_banner,
        capture_visualization,
        slugify_viz,
        trim_background,
    )

    banner_username = await resolve_banner_username(profile)

    instance_dir = output_dir / instance_slug(profile.base_url)
    instance_dir.mkdir(parents=True, exist_ok=True)
    vizes_raw = await list_visualizations_for_screenshot(profile)
    targets: list[VisualizationTarget] = []
    for entry in vizes_raw:
        uid = entry.get("id")
        if not isinstance(uid, str):
            continue
        if only is not None and uid not in only:
            continue
        display = entry.get("displayName") or entry.get("name") or uid
        viz_type_raw = entry.get("type")
        targets.append(
            VisualizationTarget(
                uid=uid,
                display_name=str(display) if isinstance(display, str) else uid,
                viz_type=str(viz_type_raw) if isinstance(viz_type_raw, str) else None,
            ),
        )

    if not targets:
        return []

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    results: list[VisualizationCaptureResult] = []
    # First target's URL lands us in the Data Visualizer app shell;
    # subsequent targets swap via hash navigation so the shell only loads
    # once.
    first = targets[0]
    async with authenticated_session(
        profile,
        headless=headless,
        navigate_to=f"/dhis-web-data-visualizer/#/{first.uid}",
    ) as (_, page):
        for index, target in enumerate(targets):
            if index > 0:
                # Swap the inner iframe's hash to the next viz without a full reload.
                await page.evaluate(
                    f"""() => {{
                        const iframe = document.querySelector('iframe');
                        if (iframe && iframe.contentWindow) {{
                            iframe.contentWindow.location.hash = '/{target.uid}';
                        }}
                    }}""",
                )
                import asyncio as _asyncio  # noqa: PLC0415

                await _asyncio.sleep(2)
            output_path = instance_dir / f"{today}-{slugify_viz(target.display_name)}.png"
            result = await capture_visualization(page, target, output_path)
            if trim:
                trim_background(output_path)
            if banner:
                add_viz_banner(
                    output_path,
                    target.display_name,
                    instance_url=profile.base_url,
                    username=banner_username,
                    viz_type=target.viz_type,
                )
            results.append(result)
    return results
