"""Version-check tests: parsing, classification, the release feed, and per-tree wiring."""

from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from types import ModuleType
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from dhis2w_core.security_core import (
    CheckStatus,
    ReleaseFeed,
    ReleaseLine,
    Severity,
    evaluate_version,
    parse_dhis2_version,
    releases,
)
from dhis2w_core.security_core.releases import RELEASES_FEED_URL, fetch_release_feed

TREES = ("v41", "v42", "v43")


@pytest.fixture(autouse=True)
def _clear_release_cache() -> Iterator[None]:
    """Drop the module-level feed cache so each test sees its own mocked feed."""
    releases._CACHE.clear()
    yield
    releases._CACHE.clear()


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _feed() -> ReleaseFeed:
    """A small feed: v43 latest (2.43.2), v42 supported (latest 2.42.5.2), v40 EOL."""
    return ReleaseFeed(
        lines=[
            ReleaseLine(
                name="2.43", version=43, supported=True, latest=True, latestPatchVersion=2, latestHotfixVersion=0
            ),
            ReleaseLine(
                name="2.42", version=42, supported=True, latest=False, latestPatchVersion=5, latestHotfixVersion=2
            ),
            ReleaseLine(
                name="2.40", version=40, supported=False, latest=False, latestPatchVersion=11, latestHotfixVersion=0
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_strips_snapshot_suffix() -> None:
    """A -SNAPSHOT build parses to its numeric parts and is flagged as a snapshot."""
    parsed = parse_dhis2_version("2.42.6-SNAPSHOT")
    assert parsed is not None
    assert (parsed.major, parsed.line, parsed.patch) == (2, 42, 6)
    assert parsed.is_snapshot


def test_parse_handles_hotfix_and_missing_patch() -> None:
    """A four-part version yields a hotfix; a two-part version defaults patch to 0."""
    assert parse_dhis2_version("2.42.5.1") == parse_dhis2_version("2.42.5.1")
    four = parse_dhis2_version("2.42.5.1")
    assert four is not None and (four.patch, four.hotfix) == (5, 1)
    short = parse_dhis2_version("2.44-SNAPSHOT")
    assert short is not None and (short.line, short.patch) == (44, 0)


@pytest.mark.parametrize("raw", [None, "", "not-a-version", "2"])
def test_parse_rejects_unusable_strings(raw: str | None) -> None:
    """Missing or unparseable version strings return None."""
    assert parse_dhis2_version(raw) is None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_stripped_version_is_info() -> None:
    """An unreported version is INFO, not a silent pass."""
    findings = evaluate_version(None, _feed())
    assert len(findings) == 1
    assert findings[0].severity is Severity.INFO


def test_eol_line_is_high() -> None:
    """A version on an unsupported line is flagged EOL (HIGH)."""
    findings = evaluate_version(parse_dhis2_version("2.40.11"), _feed())
    assert any(f.title == "End-of-life DHIS2 version" and f.severity is Severity.HIGH for f in findings)


def test_below_advisory_floor_is_high_and_suppresses_currency_note() -> None:
    """Below the advisory floor is HIGH, and the generic patch/hotfix note is suppressed."""
    findings = evaluate_version(parse_dhis2_version("2.42.5"), _feed())
    titles = {f.title for f in findings}
    assert "Running below the security-advisory patch floor" in titles
    assert "Patch or hotfix update available" not in titles


def test_latest_line_at_latest_patch_is_clean() -> None:
    """The newest line at its latest patch yields no findings at all."""
    assert evaluate_version(parse_dhis2_version("2.43.2"), _feed()) == []


def test_supported_non_latest_line_is_informational_only() -> None:
    """A supported, patched, non-latest line is at most an INFO note, never HIGH/WARN."""
    findings = evaluate_version(parse_dhis2_version("2.42.6"), _feed())
    assert findings and all(f.severity is Severity.INFO for f in findings)
    assert any(f.title == "Newer DHIS2 version line available" for f in findings)


def test_behind_on_hotfix_is_flagged() -> None:
    """Behind only on the hotfix (patch matches) still flags an update, naming the hotfix."""
    findings = evaluate_version(parse_dhis2_version("2.42.5.1"), _feed())
    currency = [f for f in findings if f.title == "Patch or hotfix update available"]
    assert currency and currency[0].severity is Severity.WARN
    assert currency[0].evidence is not None and currency[0].evidence["latest"] == "2.42.5.2"


def test_no_feed_still_applies_advisory_floor() -> None:
    """With no feed, feed-dependent checks are skipped but the static advisory floor still fires."""
    findings = evaluate_version(parse_dhis2_version("2.41.5"), None)
    assert any(f.title == "Running below the security-advisory patch floor" for f in findings)


# ---------------------------------------------------------------------------
# Release feed (egress containment)
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_release_feed_hits_only_releases_host() -> None:
    """The feed fetch contacts releases.dhis2.org and nothing else, and parses the lines."""
    route = respx.get(RELEASES_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {"name": "2.43", "version": 43, "supported": True, "latest": True, "latestPatchVersion": 1}
                ]
            },
        )
    )
    feed = await fetch_release_feed(force=True)

    assert route.called
    assert len(respx.calls) == 1
    assert respx.calls[0].request.url.host == "releases.dhis2.org"
    line = feed.line(43)
    assert line is not None and line.supported and line.latest and line.latest_patch == 1


@respx.mock
async def test_fetch_release_feed_tolerates_null_latest_patch() -> None:
    """Old EOL lines send `latestPatchVersion: null`; the feed parses them as 0, not a crash."""
    respx.get(RELEASES_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {"name": "2.43", "version": 43, "supported": True, "latest": True, "latestPatchVersion": 0},
                    {
                        "name": "2.30",
                        "version": 30,
                        "supported": False,
                        "latest": False,
                        "latestPatchVersion": None,
                        "latestHotfixVersion": None,
                    },
                ]
            },
        )
    )
    feed = await fetch_release_feed(force=True)

    old = feed.line(30)
    assert old is not None
    assert old.latest_patch == 0
    assert old.latest_hotfix == 0
    assert not old.supported


# ---------------------------------------------------------------------------
# Per-tree wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_run_version_flags_eol_from_live_feed(tree: str) -> None:
    """_run_version parses raw_version, fetches the feed, and flags an EOL line."""
    audit = _audit_module(tree)
    respx.get(RELEASES_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "versions": [
                    {"name": "2.43", "version": 43, "supported": True, "latest": True, "latestPatchVersion": 0},
                    {"name": "2.40", "version": 40, "supported": False, "latest": False, "latestPatchVersion": 11},
                ]
            },
        )
    )
    client = MagicMock()
    client.raw_version = "2.40.3"

    result = await audit._run_version(client)

    assert result.status is CheckStatus.OK
    assert any(f.title == "End-of-life DHIS2 version" for f in result.findings)


@pytest.mark.parametrize("tree", TREES)
@respx.mock
async def test_run_version_degrades_when_feed_unavailable(tree: str) -> None:
    """A feed outage degrades to a note while the static advisory floor still fires."""
    audit = _audit_module(tree)
    respx.get(RELEASES_FEED_URL).mock(side_effect=httpx.ConnectError("feed down"))
    client = MagicMock()
    client.raw_version = "2.41.5"

    result = await audit._run_version(client)

    assert result.note is not None and "release feed unavailable" in result.note
    assert any(f.title == "Running below the security-advisory patch floor" for f in result.findings)
