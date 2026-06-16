"""View-models for the `apps` plugin — update summaries, not re-exports of wire types."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UpdateOutcome(BaseModel):
    """Per-app result of an `update` run — one row per installed app."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: str
    from_version: str | None = None
    to_version: str | None = None
    status: str  # "UPDATED" / "AVAILABLE" / "UP_TO_DATE" / "SKIPPED" / "FAILED"
    reason: str | None = None


class UpdateSummary(BaseModel):
    """Aggregate of `update --all` — rows plus totals for the table footer."""

    model_config = ConfigDict(frozen=True)

    outcomes: list[UpdateOutcome]

    @property
    def updated(self) -> int:
        """Count of apps moved to a newer version."""
        return sum(1 for o in self.outcomes if o.status == "UPDATED")

    @property
    def available(self) -> int:
        """Count of apps with a newer version on the hub (dry-run only)."""
        return sum(1 for o in self.outcomes if o.status == "AVAILABLE")

    @property
    def up_to_date(self) -> int:
        """Count of apps already at the latest hub version."""
        return sum(1 for o in self.outcomes if o.status == "UP_TO_DATE")

    @property
    def skipped(self) -> int:
        """Count of apps we couldn't update (bundled / no hub id / hub miss)."""
        return sum(1 for o in self.outcomes if o.status == "SKIPPED")

    @property
    def failed(self) -> int:
        """Count of apps whose install call raised."""
        return sum(1 for o in self.outcomes if o.status == "FAILED")


class InstallTarget(BaseModel):
    """Resolved App Hub install target — the version `apps add` POSTs to `/api/appHub/{versionId}`."""

    model_config = ConfigDict(frozen=True)

    version_id: str
    app_name: str | None = None
    version: str | None = None
    resolved_from: str  # "version-id" (id was a version id) | "app-id" (id was an app id, latest version picked)
