"""View-models for the `system` plugin."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SystemSettingsSnapshot(BaseModel):
    """Raw `/api/systemSettings` key-value snapshot — every setting DHIS2 ships.

    `extra="allow"` keeps all keys. We do not reuse the generated `SystemSettings` OAS model:
    it cannot validate a live `/api/systemSettings` response (DHIS2 returns lowercase
    `keyAnalysisDisplayProperty`, which the OAS `DisplayProperty` enum rejects — BUGS.md #42).
    A raw snapshot sidesteps that for a read-only listing; `security settings` uses a typed
    projection of the same endpoint for its curated slice.
    """

    model_config = ConfigDict(extra="allow")

    def pairs(self) -> list[tuple[str, str]]:
        """Every (key, value) pair as strings, sorted by key."""
        extra = self.__pydantic_extra__ or {}
        return sorted((key, str(value)) for key, value in extra.items())
