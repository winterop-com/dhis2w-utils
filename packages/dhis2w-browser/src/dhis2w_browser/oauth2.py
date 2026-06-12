"""Playwright-driven OAuth2 login — spawn the CLI, drive the IdP form, collect tokens."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from dhis2w_client.v42.auth.oauth2 import DEFAULT_REDIRECT_PORT
from playwright.async_api import async_playwright
from pydantic import BaseModel, ConfigDict

from dhis2w_browser.session import resolve_headless

_AUTH_URL_HEADER = "Open this URL in a browser to authenticate:"
_AUTH_URL_PATTERN = re.compile(r"https?://\S+")


class OAuth2LoginResult(BaseModel):
    """Outcome of a Playwright-driven `d2w profile login --no-browser` run."""

    model_config = ConfigDict(frozen=True)

    profile: str
    auth_url: str
    returncode: int
    stdout: str
    stderr: str


async def drive_oauth2_login(
    profile_name: str,
    *,
    username: str,
    password: str,
    headless: bool | None = None,
    timeout: float = 60.0,
    env: dict[str, str] | None = None,
    cwd: Path | str | None = None,
) -> OAuth2LoginResult:
    """Run `d2w profile login <name> --no-browser` end-to-end via Playwright.

    Spawns the CLI as a subprocess, reads the DHIS2 authorize URL from its
    stderr, launches a Chromium instance, navigates to the URL, fills the
    DHIS2 login form with `(username, password)`, and waits for the CLI to
    exit — which happens once the authorization-code redirect hits the
    profile's `redirect_uri` and tokens land in the scope-appropriate
    `tokens.sqlite`.

    The `--no-browser` path is what makes this automatable — the default
    `d2w profile login` calls `webbrowser.open(url)` against the system
    browser, which Chromium can't see. See `docs/architecture/auth.md` for
    the flag's manual-use cases.

    `headless=None` honours the `DHIS2_HEADFUL=1` env fallback (matches
    the other `dhis2w-browser` helpers). `timeout` bounds the whole flow
    including the subprocess wait.

    Raises `RuntimeError` on: missing auth URL in stderr, Playwright
    failure (login-form selector drift, network), subprocess timeout,
    or non-zero CLI exit.
    """
    command = ["d2w", "profile", "login", profile_name, "--no-browser"]
    merged_env = {**os.environ, **(env or {})}
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged_env,
        cwd=str(cwd) if cwd else None,
    )
    stderr_buffer: list[str] = []
    try:
        auth_url = await asyncio.wait_for(_read_auth_url(proc, stderr_buffer), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"timed out after {timeout}s waiting for `d2w profile login` to emit the authorize URL",
        ) from exc

    try:
        await asyncio.wait_for(
            drive_login_form(auth_url, username=username, password=password, headless=resolve_headless(headless)),
            timeout=timeout,
        )
    except Exception:
        proc.kill()
        await proc.wait()
        raise

    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"`d2w profile login` did not exit within {timeout}s after the IdP form was submitted "
            "— the redirect receiver may not have captured the code",
        ) from exc

    stdout_text = stdout_raw.decode(errors="replace")
    stderr_text = "".join(stderr_buffer) + stderr_raw.decode(errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(
            f"`d2w profile login {profile_name} --no-browser` exited with code {proc.returncode}:\n{stderr_text}",
        )
    return OAuth2LoginResult(
        profile=profile_name,
        auth_url=auth_url,
        returncode=proc.returncode,
        stdout=stdout_text,
        stderr=stderr_text,
    )


async def _read_auth_url(proc: asyncio.subprocess.Process, buffer: list[str]) -> str:
    """Stream stderr until we see the `Open this URL ...` header; return the URL on the next line."""
    assert proc.stderr is not None
    saw_header = False
    while True:
        line_bytes = await proc.stderr.readline()
        if not line_bytes:
            raise RuntimeError(f"`d2w profile login` exited before emitting an authorize URL:\n{''.join(buffer)}")
        line = line_bytes.decode(errors="replace")
        buffer.append(line)
        stripped = line.strip()
        if _AUTH_URL_HEADER in stripped:
            saw_header = True
            continue
        if saw_header:
            match = _AUTH_URL_PATTERN.search(stripped)
            if match is not None:
                return match.group(0)


async def drive_login_form(auth_url: str, *, username: str, password: str, headless: bool = True) -> None:
    """Navigate Chromium to a DHIS2 authorize URL, fill the login form + consent screen.

    Lower-level companion to `drive_oauth2_login`. Takes the `auth_url`
    that some other caller already generated (e.g. `OAuth2Auth` built
    it in-process, or a CLI subprocess printed it to stderr), drives a
    Chromium instance through (1) the DHIS2 React login form and (2)
    the Spring AS "Consent required" screen, then waits for the
    browser to arrive at the configured `redirect_uri` — at which point
    whatever receiver is listening on localhost can pick up the
    authorization code.

    Use this when you're wiring Playwright into an in-process OAuth2
    flow (library-level `OAuth2Auth.redirect_capturer`); use
    `drive_oauth2_login` when you're driving the CLI subprocess
    end-to-end.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.goto(auth_url, wait_until="domcontentloaded")
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            await page.click("button[type='submit']")
            # DHIS2 v42 Spring AS serves a "Consent required" screen on the first
            # authorization for a given (user, client, scope) — the user must tick
            # the scope checkbox and click `#submit-consent` for the flow to
            # issue the authorization-code redirect. Subsequent logins with the
            # same tuple skip the consent page and redirect straight to the
            # receiver, so we wait for either terminal state.
            try:
                await page.wait_for_selector("#submit-consent", timeout=10_000)
                await page.check("input[name='scope'][value='ALL']")
                await page.click("#submit-consent")
            except Exception:
                # No consent screen — already-consented path. The authorize
                # endpoint has already fired the redirect, so page.wait_for_url
                # below will hit the receiver origin.
                pass
            # Wait for the browser to arrive at the loopback receiver. At that
            # point the CLI's redirect handler has the code and `proc.communicate`
            # on the outer helper will see the subprocess exit cleanly. The
            # `or "8765" in current` clause used to live here but it was dead
            # code — the `startswith("http://localhost:")` test is strictly
            # broader, so the second clause never decided anything. Tighten
            # to the canonical port to avoid waking early on unrelated DHIS2
            # localhost pages (e.g. /dhis-web-login/).
            await page.wait_for_url(
                lambda current: current.startswith(f"http://localhost:{DEFAULT_REDIRECT_PORT}"),
                timeout=15_000,
            )
        finally:
            await context.close()
            await browser.close()
