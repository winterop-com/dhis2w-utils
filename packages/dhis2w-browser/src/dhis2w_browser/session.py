"""Authenticated Playwright session helpers for DHIS2."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, Page, async_playwright
from pydantic import BaseModel, ConfigDict


class CookiePair(BaseModel):
    """A single `name=value` pair parsed from a raw Cookie header."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: str


def parse_cookie_header(cookie_header: str) -> list[CookiePair]:
    """Parse a raw `Cookie` header into its `name=value` pairs, splitting each pair on the first `=`.

    Pairs are separated by `;` (e.g. `JSESSIONID=abc123` or `A=1; B=2`).
    Segments with no `=` or an empty name are skipped.
    """
    pairs: list[CookiePair] = []
    for segment in cookie_header.split(";"):
        trimmed = segment.strip()
        if not trimmed or "=" not in trimmed:
            continue
        name, _, value = trimmed.partition("=")
        name = name.strip()
        if not name:
            continue
        pairs.append(CookiePair(name=name, value=value.strip()))
    return pairs


def resolve_headless(explicit: bool | None = None) -> bool:
    """Decide whether to run the browser headlessly.

    Precedence: explicit kwarg > `DHIS2_HEADFUL=1` env var (visible) > headless default.
    """
    if explicit is not None:
        return explicit
    env = os.environ.get("DHIS2_HEADFUL", "").strip().lower()
    return env not in {"1", "true", "yes", "on"}


@asynccontextmanager
async def logged_in_page(
    base_url: str,
    username: str,
    password: str,
    *,
    headless: bool | None = None,
    timeout_ms: int = 30_000,
) -> AsyncGenerator[tuple[BrowserContext, Page]]:
    """Yield an authenticated Playwright `(context, page)` tuple logged into DHIS2.

    Navigates to `{base_url}/dhis-web-login/`, fills the React login form, and
    waits for the post-login redirect. On exit the browser context is closed.

    Prefer `session_from_cookie(...)` when you already have a `JSESSIONID` —
    it skips the form interaction entirely. This helper is the fallback for
    flows that genuinely need the React login to happen (e.g. minting a PAT
    on an instance where Basic API auth is disabled).
    """
    url = base_url.rstrip("/")
    resolved_headless = resolve_headless(headless)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=resolved_headless)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.goto(f"{url}/dhis-web-login/", timeout=timeout_ms)
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            await page.click("button[type='submit']")
            await _wait_until_authenticated(page, url, timeout_ms=timeout_ms)
            yield context, page
        finally:
            await context.close()
            await browser.close()


async def _wait_until_authenticated(page: Page, url: str, *, timeout_ms: int) -> None:
    """Block until `GET /api/me` returns JSON, i.e. the session is authenticated.

    Matching on the URL alone is fragile across DHIS2 majors — v41 lands on
    `/dhis-web-commons-stream/`, v42 on the apps shell at `/`, v43 first
    redirects `/dhis-web-login/` to `/login/` and then to `/apps/login`. The
    only stable signal is "the server treats my cookie as authenticated",
    which is exactly what `/api/me` with `Accept: application/json` checks.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            response = await page.request.get(f"{url}/api/me", headers={"Accept": "application/json"})
        except Exception:  # noqa: BLE001 — Playwright surfaces network errors during the post-login navigation window
            response = None
        if response is not None and response.ok and "json" in (response.headers.get("content-type") or ""):
            return
        await asyncio.sleep(0.25)
    raise TimeoutError(f"DHIS2 session never authenticated within {timeout_ms}ms at {url}")


@asynccontextmanager
async def _browser_with_cookies(
    base_url: str,
    cookies: list[CookiePair],
    *,
    headless: bool | None,
    navigate_to: str | None,
    timeout_ms: int,
) -> AsyncGenerator[tuple[BrowserContext, Page]]:
    """Launch Playwright, inject every cookie pair against `base_url`, and land on `navigate_to`.

    Each pair is added with the base URL so Playwright derives the cookie
    domain, path, and `secure` flag from the scheme/host. The context is
    always closed on exit.
    """
    url = base_url.rstrip("/")
    resolved_headless = resolve_headless(headless)
    landing = navigate_to or "/"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=resolved_headless)
        context = await browser.new_context()
        await context.add_cookies(
            [{"name": pair.name, "value": pair.value, "url": url} for pair in cookies],
        )
        try:
            page = await context.new_page()
            await page.goto(f"{url}{landing}", timeout=timeout_ms)
            yield context, page
        finally:
            await context.close()
            await browser.close()


@asynccontextmanager
async def session_from_cookie(
    base_url: str,
    jsessionid: str,
    *,
    headless: bool | None = None,
    navigate_to: str | None = None,
    timeout_ms: int = 30_000,
) -> AsyncGenerator[tuple[BrowserContext, Page]]:
    """Yield a Playwright `(context, page)` with a pre-minted `JSESSIONID` cookie injected.

    Caller is expected to have obtained `jsessionid` via a cheap HTTP call
    (e.g. `GET /api/me` with `Authorization: Basic`) — DHIS2 sets the cookie
    in the response's `Set-Cookie` header on any authenticated request. No
    React login form interaction happens here, which makes this flow fast,
    fully headless-friendly, and independent of form-selector drift.

    `navigate_to` picks the landing URL (defaults to `/` — DHIS2 redirects to
    the apps shell). Pass e.g. `/dhis-web-dashboard/` to land directly in
    the dashboard app.
    """
    async with _browser_with_cookies(
        base_url,
        [CookiePair(name="JSESSIONID", value=jsessionid)],
        headless=headless,
        navigate_to=navigate_to,
        timeout_ms=timeout_ms,
    ) as (context, page):
        yield context, page


@asynccontextmanager
async def session_from_cookie_header(
    base_url: str,
    cookie_header: str,
    *,
    headless: bool | None = None,
    navigate_to: str | None = None,
    timeout_ms: int = 30_000,
) -> AsyncGenerator[tuple[BrowserContext, Page]]:
    """Yield a Playwright `(context, page)` with every pair from a raw Cookie header injected.

    Parses `cookie_header` (`name=value` pairs separated by `;`, e.g.
    `JSESSIONID=abc123` or `A=1; B=2`) and injects each pair into a fresh
    browser context — the session-profile fast path where the caller already
    holds the session material and no login is needed. Raises `ValueError`
    when the header carries no usable `name=value` pairs.
    """
    pairs = parse_cookie_header(cookie_header)
    if not pairs:
        raise ValueError(f"cookie header {cookie_header!r} carries no name=value pairs")
    async with _browser_with_cookies(
        base_url,
        pairs,
        headless=headless,
        navigate_to=navigate_to,
        timeout_ms=timeout_ms,
    ) as (context, page):
        yield context, page
