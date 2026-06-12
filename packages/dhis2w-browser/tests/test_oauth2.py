"""Unit tests for `dhis2w_browser.oauth2._read_auth_url` — stderr-parser contract."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dhis2w_browser.oauth2 import _read_auth_url

# The exact stderr block `d2w profile login --no-browser` emits today.
# Kept verbatim so this test fails if the CLI copy drifts out of sync with
# the parser.
_CLI_STDERR_SNIPPET = (
    "starting OAuth2 login for 'local_oidc' -> http://localhost:8080 (no-browser mode) ...\n"
    "\n"
    "Open this URL in a browser to authenticate:\n"
    "\n"
    "  http://localhost:8080/oauth2/authorize?client_id=abc&response_type=code&"
    "redirect_uri=http%3A%2F%2Flocalhost%3A8765&scope=ALL&state=xyz&"
    "code_challenge=chall&code_challenge_method=S256\n"
    "\n"
    "Waiting for redirect to http://localhost:8765 ...\n"
)


class _FakeStream:
    """Async stand-in for `asyncio.subprocess.Process.stderr` — yields line-by-line."""

    def __init__(self, payload: str) -> None:
        self._lines = [line + "\n" for line in payload.splitlines()]
        self._index = 0

    async def readline(self) -> bytes:
        if self._index >= len(self._lines):
            return b""
        line = self._lines[self._index]
        self._index += 1
        return line.encode()


class _FakeProcess:
    """Subset of `asyncio.subprocess.Process` the parser needs."""

    def __init__(self, stderr_text: str) -> None:
        self.stderr = _FakeStream(stderr_text)


async def test_read_auth_url_extracts_url_from_cli_stderr() -> None:
    """Given the CLI's stderr block, the parser returns the authorize URL."""
    buffer: list[str] = []
    url = await _read_auth_url(_FakeProcess(_CLI_STDERR_SNIPPET), buffer)  # type: ignore[arg-type]
    assert url.startswith("http://localhost:8080/oauth2/authorize?")
    assert "client_id=abc" in url
    assert "state=xyz" in url
    assert "code_challenge_method=S256" in url
    # `buffer` should hold every stderr line we consumed up to + including the URL line.
    assert any("Open this URL" in line for line in buffer)
    assert any("authorize" in line for line in buffer)


async def test_read_auth_url_raises_when_proc_exits_without_url() -> None:
    """EOF on stderr before the header → RuntimeError with the captured buffer."""
    buffer: list[str] = []
    with pytest.raises(RuntimeError, match="exited before emitting an authorize URL"):
        await _read_auth_url(_FakeProcess("unrelated prep output\n"), buffer)  # type: ignore[arg-type]
    assert "unrelated prep output" in buffer[0]


async def test_read_auth_url_skips_header_only_lines() -> None:
    """Blank lines and non-URL prose between the header and the URL don't confuse the parser."""
    payload = (
        "some prep output\n"
        "Open this URL in a browser to authenticate:\n"
        "\n"
        "  (this line has no URL)\n"
        "  https://idp.example/authorize?state=ok\n"
    )
    buffer: list[str] = []
    url = await asyncio.wait_for(
        _read_auth_url(_FakeProcess(payload), buffer),  # type: ignore[arg-type]
        timeout=1.0,
    )
    assert url == "https://idp.example/authorize?state=ok"


def test_oauth2_login_result_is_frozen_pydantic_model() -> None:
    """`OAuth2LoginResult` is a frozen BaseModel (not a dataclass) per repo rules."""
    from dhis2w_browser.oauth2 import OAuth2LoginResult

    result = OAuth2LoginResult(
        profile="x",
        auth_url="http://x",
        returncode=0,
        stdout="",
        stderr="",
    )
    config: dict[str, Any] = dict(result.model_config)
    assert config.get("frozen") is True
