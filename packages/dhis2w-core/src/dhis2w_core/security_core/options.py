"""User-tunable audit options threaded through the security audit entry points."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class AuditOptions(BaseModel):
    """The user-tunable knobs for one audit run, collapsed into a single value the binders read.

    Carries only user-chosen options. Runtime context (`now`, `generated_at`, the graph sink, the console)
    is passed separately so the core stays deterministic with the clock supplied by the caller.
    """

    model_config = ConfigDict(frozen=True)

    stale_days: int
    max_password_age_days: int
    two_factor_detail: bool
    max_objects: int
    dhis_conf_path: Path | None = None
