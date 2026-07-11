"""DHIS2 session-cookie authentication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SessionCookieAuth(BaseModel):
    """DHIS2 browser session — sent as a raw Cookie header (e.g. Cookie: JSESSIONID=<id>)."""

    model_config = ConfigDict(frozen=True)

    cookie: str

    async def headers(self) -> dict[str, str]:
        """Return the raw Cookie header."""
        return {"Cookie": self.cookie}

    async def refresh_if_needed(self) -> None:
        """Session cookies are managed by the browser; nothing to refresh."""
        return None
