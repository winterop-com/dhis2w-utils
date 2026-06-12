"""Shared types for the doctor plugin — probe result + aggregated report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProbeStatus = Literal["pass", "warn", "fail", "skip"]

# Three probe categories map to three sub-commands under `d2w doctor`:
# - metadata: workspace-specific instance-health checks (data sets with no DEs, etc.)
# - integrity: delegates to DHIS2's own /api/dataIntegrity/summary — one ProbeResult per DHIS2 check
# - bugs: verifies BUGS.md workarounds still apply (workspace drift detection)
ProbeCategory = Literal["metadata", "integrity", "bugs"]


class ProbeResult(BaseModel):
    """Outcome of one doctor probe.

    `offending_uids` lists the UIDs a metadata probe found (e.g. dataSets with
    zero dataElements) so operators can jump straight to fixing them instead
    of re-running the query themselves.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    category: ProbeCategory
    status: ProbeStatus
    message: str
    bugs_ref: str | None = None
    detail: str | None = None
    offending_uids: list[str] = Field(default_factory=list)


class DoctorReport(BaseModel):
    """Aggregate of every probe run against an instance."""

    profile_name: str | None = None
    base_url: str
    dhis2_version: str | None = None
    probes: list[ProbeResult] = Field(default_factory=list)

    @property
    def pass_count(self) -> int:
        """Number of `pass` probes."""
        return sum(1 for probe in self.probes if probe.status == "pass")

    @property
    def warn_count(self) -> int:
        """Number of `warn` probes."""
        return sum(1 for probe in self.probes if probe.status == "warn")

    @property
    def fail_count(self) -> int:
        """Number of `fail` probes."""
        return sum(1 for probe in self.probes if probe.status == "fail")

    @property
    def skip_count(self) -> int:
        """Number of `skip` probes."""
        return sum(1 for probe in self.probes if probe.status == "skip")
