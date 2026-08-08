"""Unit tests for the serve settings: defaults and immutability."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_fhir_serve.settings import ServeSettings
from pydantic import ValidationError


def test_defaults(tmp_path: Path) -> None:
    """Only the project directory is required; the rest default to the compiled, non-strict facade."""
    settings = ServeSettings(project_dir=tmp_path)

    assert settings.project_dir == tmp_path
    assert settings.live is False
    assert settings.profile is None
    assert settings.strict_codes is False


def test_explicit_values(tmp_path: Path) -> None:
    """Every field is settable for a live, profile-bound, strict facade."""
    settings = ServeSettings(project_dir=tmp_path, live=True, profile="probe", strict_codes=True)

    assert settings.live is True
    assert settings.profile == "probe"
    assert settings.strict_codes is True


def test_frozen(tmp_path: Path) -> None:
    """Settings are read-only once built - the app factory never rewrites what it was handed."""
    settings = ServeSettings(project_dir=tmp_path)

    with pytest.raises(ValidationError):
        settings.live = True


def test_project_dir_is_required() -> None:
    """There is no default project - a facade always serves a named one."""
    with pytest.raises(ValidationError):
        ServeSettings()  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
