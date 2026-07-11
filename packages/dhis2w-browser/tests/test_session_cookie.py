"""Unit tests for raw-Cookie-header parsing and cookie injection in `dhis2w_browser.session`.

The Playwright chain is faked so these run without Chromium binaries — they
assert which cookies land in the browser context and where the page navigates.
"""

from __future__ import annotations

import pytest
from dhis2w_browser import session
from dhis2w_browser.session import CookiePair, parse_cookie_header


def test_parse_cookie_header_single_pair() -> None:
    """A lone `name=value` header yields one pair."""
    assert parse_cookie_header("JSESSIONID=abc123") == [CookiePair(name="JSESSIONID", value="abc123")]


def test_parse_cookie_header_multi_pair() -> None:
    """Semicolon-separated pairs each become their own `CookiePair`."""
    assert parse_cookie_header("A=1; B=2") == [
        CookiePair(name="A", value="1"),
        CookiePair(name="B", value="2"),
    ]


def test_parse_cookie_header_splits_on_first_equals() -> None:
    """A value containing `=` is preserved — only the first `=` separates name from value."""
    assert parse_cookie_header("token=ab=cd==") == [CookiePair(name="token", value="ab=cd==")]


def test_parse_cookie_header_trims_and_skips_junk() -> None:
    """Whitespace is trimmed; empty segments and segments without `=` are skipped."""
    assert parse_cookie_header("  JSESSIONID = abc  ; ; junk ; B=2 ") == [
        CookiePair(name="JSESSIONID", value="abc"),
        CookiePair(name="B", value="2"),
    ]


def test_parse_cookie_header_empty_yields_no_pairs() -> None:
    """A blank header yields no pairs."""
    assert parse_cookie_header("   ") == []


class _FakePage:
    """Records the URL and timeout a `goto` lands on."""

    def __init__(self) -> None:
        self.goto_url: str | None = None
        self.goto_timeout: int | None = None

    async def goto(self, url: str, *, timeout: int) -> None:
        """Record the navigation target."""
        self.goto_url = url
        self.goto_timeout = timeout


class _FakeContext:
    """Records injected cookies and whether it was closed."""

    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.added_cookies: list[dict[str, str]] | None = None
        self.closed = False

    async def add_cookies(self, cookies: list[dict[str, str]]) -> None:
        """Record the cookie list handed to Playwright."""
        self.added_cookies = cookies

    async def new_page(self) -> _FakePage:
        """Return the fake page."""
        return self._page

    async def close(self) -> None:
        """Mark the context closed."""
        self.closed = True


class _FakeBrowser:
    """Yields a single fake context and records headless + close."""

    def __init__(self, context: _FakeContext) -> None:
        self._context = context
        self.headless: bool | None = None
        self.closed = False

    async def new_context(self) -> _FakeContext:
        """Return the fake context."""
        return self._context

    async def close(self) -> None:
        """Mark the browser closed."""
        self.closed = True


class _FakeChromium:
    """Stand-in for `playwright.chromium` — records the headless flag on launch."""

    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser

    async def launch(self, *, headless: bool) -> _FakeBrowser:
        """Return the fake browser, recording the headless flag."""
        self._browser.headless = headless
        return self._browser


class _FakePlaywright:
    """Exposes `.chromium` like the real Playwright driver."""

    def __init__(self, browser: _FakeBrowser) -> None:
        self.chromium = _FakeChromium(browser)


class _FakePlaywrightCM:
    """Async context manager stand-in for `async_playwright()`."""

    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser

    async def __aenter__(self) -> _FakePlaywright:
        return _FakePlaywright(self._browser)

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.fixture
def fake_browser(monkeypatch: pytest.MonkeyPatch) -> _FakeBrowser:
    """Patch `async_playwright` with a fake chain and return the fake browser."""
    page = _FakePage()
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    monkeypatch.setattr(session, "async_playwright", lambda: _FakePlaywrightCM(browser))
    return browser


async def test_session_from_cookie_header_injects_single_pair(fake_browser: _FakeBrowser) -> None:
    """A single-pair header injects one cookie derived against the base URL."""
    context = fake_browser._context  # noqa: SLF001 — test reaches into the fake it owns
    page = context._page  # noqa: SLF001 — test reaches into the fake it owns
    async with session.session_from_cookie_header(
        "https://play.example/",
        "JSESSIONID=abc123",
        navigate_to="/dhis-web-dashboard/",
    ):
        pass
    assert context.added_cookies == [{"name": "JSESSIONID", "value": "abc123", "url": "https://play.example"}]
    assert page.goto_url == "https://play.example/dhis-web-dashboard/"
    assert context.closed
    assert fake_browser.closed


async def test_session_from_cookie_header_injects_multi_pair(fake_browser: _FakeBrowser) -> None:
    """A multi-pair header injects every pair against the base URL."""
    context = fake_browser._context  # noqa: SLF001 — test reaches into the fake it owns
    page = context._page  # noqa: SLF001 — test reaches into the fake it owns
    async with session.session_from_cookie_header(
        "https://play.example",
        "JSESSIONID=abc123; XSRF-TOKEN=deadbeef",
    ):
        pass
    assert context.added_cookies == [
        {"name": "JSESSIONID", "value": "abc123", "url": "https://play.example"},
        {"name": "XSRF-TOKEN", "value": "deadbeef", "url": "https://play.example"},
    ]
    assert page.goto_url == "https://play.example/"


async def test_session_from_cookie_header_empty_raises(fake_browser: _FakeBrowser) -> None:
    """A header with no usable pairs raises before any browser launch."""
    with pytest.raises(ValueError, match="no name=value pairs"):
        async with session.session_from_cookie_header("https://play.example", "   "):
            pass


async def test_session_from_cookie_injects_jsessionid(fake_browser: _FakeBrowser) -> None:
    """The single-JSESSIONID helper still injects exactly one cookie."""
    context = fake_browser._context  # noqa: SLF001 — test reaches into the fake it owns
    async with session.session_from_cookie("http://localhost:8080", "sess42"):
        pass
    assert context.added_cookies == [{"name": "JSESSIONID", "value": "sess42", "url": "http://localhost:8080"}]
