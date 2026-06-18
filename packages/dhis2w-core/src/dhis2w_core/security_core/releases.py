"""The public DHIS2 stable-release feed (releases.dhis2.org), parsed and TTL-cached.

This is the audit's only direct external egress (see `guardrails`): the feed
that tells us which version lines are still supported and the latest patch on
each. Everything else the audit reads comes from the target DHIS2 instance.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

# The canonical stable-release feed. The only host the audit contacts directly
# besides the target instance.
RELEASES_FEED_URL = "https://releases.dhis2.org/v1/versions/stable.json"

_TTL_SECONDS = 3600.0
_CACHE: dict[str, tuple[float, ReleaseFeed]] = {}


class ReleaseLine(BaseModel):
    """One DHIS2 version line (e.g. 2.42) from the stable-release feed."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    name: str = ""
    line: int = Field(default=0, alias="version")
    supported: bool = False
    latest: bool = False
    latest_patch: int = Field(default=0, alias="latestPatchVersion")
    latest_hotfix: int = Field(default=0, alias="latestHotfixVersion")

    @field_validator("latest_patch", "latest_hotfix", mode="before")
    @classmethod
    def _null_count_is_zero(cls, value: object) -> object:
        """Old EOL lines carry null patch/hotfix counts; treat them as 0."""
        return 0 if value is None else value


class ReleaseFeed(BaseModel):
    """The parsed stable-release feed: every known version line."""

    model_config = ConfigDict(frozen=True)

    lines: list[ReleaseLine] = []

    def line(self, number: int) -> ReleaseLine | None:
        """Return the release line matching `number`, or None when the feed omits it."""
        return next((entry for entry in self.lines if entry.line == number), None)

    def latest_line(self) -> int | None:
        """Return the newest version line (the `latest` flag, else the max line number)."""
        flagged = [entry.line for entry in self.lines if entry.latest]
        if flagged:
            return max(flagged)
        return max((entry.line for entry in self.lines), default=None)


class _FeedPayload(BaseModel):
    """Wire envelope for the stable-release feed."""

    model_config = ConfigDict(extra="ignore")

    versions: list[ReleaseLine] = []


async def fetch_release_feed(*, force: bool = False) -> ReleaseFeed:
    """Fetch and cache the stable-release feed, refreshing once the TTL lapses."""
    elapsed = time.monotonic()
    cached = _CACHE.get(RELEASES_FEED_URL)
    if cached is not None and not force and (elapsed - cached[0]) < _TTL_SECONDS:
        return cached[1]
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=10.0)) as http:
        response = await http.get(RELEASES_FEED_URL, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = _FeedPayload.model_validate(response.json())
    feed = ReleaseFeed(lines=list(payload.versions))
    _CACHE[RELEASES_FEED_URL] = (elapsed, feed)
    return feed
