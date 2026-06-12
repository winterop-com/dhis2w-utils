"""Unit tests for `instance_slug` — the per-instance output-dir namespace."""

from __future__ import annotations

from dhis2w_core.v42.plugins.browser.service import instance_slug


def test_strips_scheme_and_colonises_port() -> None:
    """Every URL form common in profiles maps to a filesystem-safe slug."""
    assert instance_slug("http://localhost:8080") == "localhost-8080"
    assert instance_slug("https://play.dhis2.org/40") == "play.dhis2.org-40"
    assert instance_slug("https://play.dhis2.org/40/") == "play.dhis2.org-40"


def test_preserves_dots_and_hyphens() -> None:
    """Hostnames carry dots + hyphens; the slug keeps them intact."""
    assert instance_slug("https://data.example-instance.org") == "data.example-instance.org"


def test_falls_back_to_placeholder_on_empty_input() -> None:
    """Edge case — caller passing an empty URL still gets a usable directory name."""
    assert instance_slug("") == "instance"
    assert instance_slug("http://") == "instance"
