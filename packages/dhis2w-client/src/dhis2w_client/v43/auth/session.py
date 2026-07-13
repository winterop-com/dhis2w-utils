"""DHIS2 session-cookie authentication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from pydantic_core.core_schema import SerializationInfo


class SessionCookieAuth(BaseModel):
    """DHIS2 browser session — sent as a raw Cookie header (e.g. Cookie: JSESSIONID=<id>).

    The cookie stays out of `repr()` (`Field(repr=False)`) and is masked in
    `model_dump()`; pass `context={"reveal": True}` to `model_dump()` to reveal
    it. `headers()` reads the plain attribute to build the Cookie header.
    """

    model_config = ConfigDict(frozen=True)

    cookie: str = Field(repr=False)

    xsrf_token: str | None = Field(default=None, repr=False)
    """Double-submit CSRF token echoed as the `X-XSRF-TOKEN` header.

    DHIS2 issues an `XSRF-TOKEN` cookie and expects it echoed back as the
    `X-XSRF-TOKEN` header; `None` means the instance doesn't require CSRF, so
    the header is omitted — inert by default. Masked like `cookie`.
    """

    @field_serializer("cookie", "xsrf_token")
    def _redact(self, value: str | None, info: SerializationInfo) -> str | None:
        """Mask the cookie and xsrf token unless serialization runs with `context={"reveal": True}`."""
        if value is None:
            return None
        if info.context and info.context.get("reveal"):
            return value
        return "**********"

    @field_validator("xsrf_token", mode="before")
    @classmethod
    def _normalize_xsrf_token(cls, value: object) -> str | None:
        """Trim the CSRF token and reject one carrying ASCII control characters; empty normalizes to None.

        `xsrf_token` is optional and inert-by-default: an empty or
        whitespace-only value normalizes to `None` (header omitted) rather than
        raising, so an empty token behaves exactly like an unset one. A non-empty
        value that still carries control characters after trimming is a genuine
        copy-paste error and is rejected — failing fast instead of emitting a
        malformed `X-XSRF-TOKEN` header at send time.
        """
        if value is None:
            return None
        raw = value
        if not isinstance(raw, str):
            raise ValueError("session xsrf token must be a string")
        normalized = raw.strip()
        if not normalized:
            return None
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
            raise ValueError(
                "session xsrf token contains control characters or stray line breaks — "
                "re-copy the value from the browser without embedded newlines, carriage returns, or tabs"
            )
        return normalized

    async def headers(self) -> dict[str, str]:
        """Return the raw Cookie header, plus `X-XSRF-TOKEN` when a CSRF token is set."""
        headers = {"Cookie": self.cookie}
        if self.xsrf_token is not None:
            headers["X-XSRF-TOKEN"] = self.xsrf_token
        return headers

    async def refresh_if_needed(self) -> None:
        """Session cookies are managed by the browser; nothing to refresh."""
        return None
