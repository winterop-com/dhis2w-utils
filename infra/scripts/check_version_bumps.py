"""Detect newer DHIS2 patch releases on Docker Hub for the pinned minors.

Reads `infra/versions.env` (`DHIS2_V<minor>=<tag>`; a line with an inline
`# held` comment is skipped — see the v42 mapView hold, BUGS.md #43), queries
the `dhis2/core` Docker Hub tag list for the latest stable patch in each
non-held minor, and reports which pins are behind. In GitHub Actions (when
`GITHUB_OUTPUT` is set) it also emits a `bumps` JSON array so the bump workflow
can fan out a bump + codegen-regen PR per version.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

_ENDPOINT = "https://hub.docker.com/v2/repositories/dhis2/core/tags"
# Stable DHIS2 release tags only: `2.43.0.1` — exclude `-rc` / `-eos` / `-SNAPSHOT`.
_STABLE_RE = re.compile(r"^2\.(\d+)\.\d+(?:\.\d+)?$")
_PIN_RE = re.compile(r"^DHIS2_V(\d+)\s*=\s*(\S+)(.*)$")
_MAX_PAGES = 6


class Pin(BaseModel):
    """One pinned minor read from versions.env."""

    model_config = ConfigDict(frozen=True)

    minor: int
    tag: str
    held: bool


class Bump(BaseModel):
    """A minor whose pin is behind the latest stable patch on Docker Hub."""

    model_config = ConfigDict(frozen=True)

    minor: int
    tree: str
    current: str
    latest: str


def _version_key(tag: str) -> tuple[int, ...]:
    """Return the numeric tuple for a dotted version tag, for ordering."""
    return tuple(int(part) for part in tag.split("."))


def read_pins(versions_env: Path) -> list[Pin]:
    """Parse `DHIS2_V<minor>=<tag>` lines; an inline `# held` marks a hold."""
    pins: list[Pin] = []
    for line in versions_env.read_text(encoding="utf-8").splitlines():
        match = _PIN_RE.match(line.strip())
        if match is None:
            continue
        pins.append(Pin(minor=int(match.group(1)), tag=match.group(2), held="# held" in match.group(3).lower()))
    return pins


def fetch_latest_per_minor() -> dict[int, str]:
    """Return the latest stable `dhis2/core` patch tag for each minor on Docker Hub."""
    latest: dict[int, tuple[tuple[int, ...], str]] = {}
    url: str | None = _ENDPOINT
    page = 0
    with httpx.Client(timeout=20.0) as client:
        while url is not None and page < _MAX_PAGES:
            response = client.get(url, params={"page_size": 100} if page == 0 else None)
            response.raise_for_status()
            payload = response.json()
            for entry in payload.get("results", []):
                name = str(entry.get("name", ""))
                match = _STABLE_RE.match(name)
                if match is None:
                    continue
                minor = int(match.group(1))
                key = _version_key(name)
                if minor not in latest or key > latest[minor][0]:
                    latest[minor] = (key, name)
            url = payload.get("next")
            page += 1
    return {minor: name for minor, (_key, name) in latest.items()}


def find_bumps(pins: list[Pin], latest: dict[int, str]) -> list[Bump]:
    """Return a Bump for every non-held pin behind the latest stable patch."""
    bumps: list[Bump] = []
    for pin in pins:
        if pin.held:
            continue
        newest = latest.get(pin.minor)
        if newest is not None and _version_key(newest) > _version_key(pin.tag):
            bumps.append(Bump(minor=pin.minor, tree=f"v{pin.minor}", current=pin.tag, latest=newest))
    return bumps


def main() -> int:
    """Print a human summary and, under GitHub Actions, emit the `bumps` JSON output."""
    versions_env = Path(__file__).resolve().parent.parent / "versions.env"
    pins = read_pins(versions_env)
    try:
        latest = fetch_latest_per_minor()
    except httpx.HTTPError as exc:
        print(f"!!! Failed to reach Docker Hub: {exc}", file=sys.stderr)
        return 1

    bumps = find_bumps(pins, latest)
    for pin in pins:
        newest = latest.get(pin.minor, "?")
        if pin.held:
            print(f"  v{pin.minor}: {pin.tag} (held — latest {newest}, see BUGS.md)")
        elif any(b.minor == pin.minor for b in bumps):
            print(f"  v{pin.minor}: {pin.tag} -> {newest}  BUMP AVAILABLE")
        else:
            print(f"  v{pin.minor}: {pin.tag} (current)")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        payload = json.dumps([bump.model_dump() for bump in bumps])
        with Path(github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"bumps={payload}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
