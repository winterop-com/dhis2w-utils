"""HTTP Basic authentication provider."""

from __future__ import annotations

import base64

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic_core.core_schema import SerializationInfo


class BasicAuth(BaseModel):
    """HTTP Basic auth — username/password encoded into Authorization header.

    The password stays out of `repr()` (`Field(repr=False)`) and is masked in
    `model_dump()`; pass `context={"reveal": True}` to `model_dump()` to reveal
    it. `headers()` reads the plain attribute to build the Authorization header.
    """

    model_config = ConfigDict(frozen=True)

    username: str
    password: str = Field(repr=False)

    @field_serializer("password")
    def _redact(self, value: str | None, info: SerializationInfo) -> str | None:
        """Mask the password unless serialization runs with `context={"reveal": True}`."""
        if value is None:
            return None
        if info.context and info.context.get("reveal"):
            return value
        return "**********"

    async def headers(self) -> dict[str, str]:
        """Return the Authorization: Basic header for this credential pair."""
        raw = f"{self.username}:{self.password}".encode()
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}

    async def refresh_if_needed(self) -> None:
        """Basic auth has no expiry; nothing to refresh."""
        return None
