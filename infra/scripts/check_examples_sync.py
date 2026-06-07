"""Guard: every v42 example must have a v41 + v43 counterpart (same relative path).

v42 is the canonical baseline. Version-specific examples may exist as extras in v41/v43, but a
common example added under v42 without its siblings is drift (CLAUDE.md rule 15). Source files
only (.py/.sh); build artifacts are ignored.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "examples"
SUFFIXES = {".py", ".sh"}

# Examples a version legitimately omits (documented divergence, not drift). v43 event/enrollment
# analytics behaves differently from v41/v42 on the seeded program — the example errors there, so
# v43 has no counterpart by design (revisit if v43 event analytics is reconciled).
OMITTED: dict[str, set[Path]] = {
    "v43": {
        Path("client/analytics_events_enrollments.py"),
        Path("mcp/analytics_events_enrollments.py"),
    },
}


def _source_set(version: str) -> set[Path]:
    base = ROOT / version
    return {p.relative_to(base) for p in base.rglob("*") if p.suffix in SUFFIXES and "__pycache__" not in p.parts}


def main() -> int:
    v42 = _source_set("v42")
    missing: list[str] = []
    for version in ("v41", "v43"):
        for rel in sorted(v42 - _source_set(version) - OMITTED.get(version, set())):
            missing.append(f"examples/{version}/{rel} (present in v42)")
    if missing:
        print("Example drift — v42 examples missing a per-version counterpart:")
        for line in missing:
            print(f"  - {line}")
        return 1
    print(f"examples in sync: all {len(v42)} v42 examples have v41 + v43 counterparts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
