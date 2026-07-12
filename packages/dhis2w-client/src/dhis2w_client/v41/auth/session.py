"""DHIS2 session-cookie authentication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic_core.core_schema import SerializationInfo


class SessionCookieAuth(BaseModel):
    """DHIS2 browser session — sent as a raw Cookie header (e.g. Cookie: JSESSIONID=<id>).

    The cookie stays out of `repr()` (`Field(repr=False)`) and is masked in
    `model_dump()`; pass `context={"reveal": True}` to `model_dump()` to reveal
    it. `headers()` reads the plain attribute to build the Cookie header.
    """

    model_config = ConfigDict(frozen=True)

    cookie: str = Field(repr=False)

    @field_serializer("cookie")
    def _redact(self, value: str | None, info: SerializationInfo) -> str | None:
        """Mask the cookie unless serialization runs with `context={"reveal": True}`."""
        if value is None:
            return None
        if info.context and info.context.get("reveal"):
            return value
        return "**********"

    async def headers(self) -> dict[str, str]:
        """Return the raw Cookie header."""
        return {"Cookie": self.cookie}

    async def refresh_if_needed(self) -> None:
        """Session cookies are managed by the browser; nothing to refresh."""
        return None
