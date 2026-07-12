"""DHIS2 Personal Access Token authentication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic_core.core_schema import SerializationInfo


class PatAuth(BaseModel):
    """DHIS2 Personal Access Token — sent as Authorization: ApiToken <pat>.

    The token stays out of `repr()` (`Field(repr=False)`) and is masked in
    `model_dump()`; pass `context={"reveal": True}` to `model_dump()` to reveal
    it. `headers()` reads the plain attribute to build the Authorization header.
    """

    model_config = ConfigDict(frozen=True)

    token: str = Field(repr=False)

    @field_serializer("token")
    def _redact(self, value: str | None, info: SerializationInfo) -> str | None:
        """Mask the token unless serialization runs with `context={"reveal": True}`."""
        if value is None:
            return None
        if info.context and info.context.get("reveal"):
            return value
        return "**********"

    async def headers(self) -> dict[str, str]:
        """Return the Authorization: ApiToken header."""
        return {"Authorization": f"ApiToken {self.token}"}

    async def refresh_if_needed(self) -> None:
        """PATs are long-lived; nothing to refresh."""
        return None
