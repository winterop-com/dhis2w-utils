"""Unit tests for the Profile model + profile_from_env_raw in dhis2w-client."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_client import Dhis2, Profile, profile_from_env_raw
from dhis2w_client.profile import (
    PROFILE_NAME_MAX_LEN,
    InvalidProfileNameError,
    validate_profile_name,
)
from pydantic import ValidationError


def _clear_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate the test from real DHIS2_* env vars so only what we set applies."""
    for key in (
        "DHIS2_PROFILE",
        "DHIS2_URL",
        "DHIS2_PAT",
        "DHIS2_USERNAME",
        "DHIS2_PASSWORD",
        "DHIS2_VERSION",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)


def test_profile_construct_pat() -> None:
    """Profile construct pat."""
    profile = Profile(base_url="http://localhost:8080", auth="pat", token="d2p_test")
    assert profile.auth == "pat"
    assert profile.token == "d2p_test"
    assert profile.username is None


def test_profile_construct_basic() -> None:
    """Profile construct basic."""
    profile = Profile(base_url="http://localhost:8080", auth="basic", username="admin", password="district")
    assert profile.username == "admin"
    assert profile.password == "district"


def test_profile_is_frozen() -> None:
    """Profile is frozen."""
    profile = Profile(base_url="http://localhost:8080", auth="pat", token="t")
    with pytest.raises(ValidationError):
        profile.token = "other"


def test_profile_from_env_raw_pat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env raw pat."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080/")
    monkeypatch.setenv("DHIS2_PAT", "d2p_env")
    profile = profile_from_env_raw()
    assert profile is not None
    assert profile.base_url == "http://localhost:8080"
    assert profile.auth == "pat"
    assert profile.token == "d2p_env"


def test_profile_from_env_raw_basic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env raw basic."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_USERNAME", "admin")
    monkeypatch.setenv("DHIS2_PASSWORD", "district")
    profile = profile_from_env_raw()
    assert profile is not None
    assert profile.auth == "basic"


def test_profile_from_env_raw_pat_beats_basic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env raw pat beats basic."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "d2p_token")
    monkeypatch.setenv("DHIS2_USERNAME", "admin")
    monkeypatch.setenv("DHIS2_PASSWORD", "district")
    profile = profile_from_env_raw()
    assert profile is not None
    assert profile.auth == "pat"


def test_profile_from_env_raw_returns_none_when_no_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env raw returns none when no url."""
    _clear_env(monkeypatch, tmp_path)
    assert profile_from_env_raw() is None


def test_profile_from_env_raw_returns_none_when_no_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env raw returns none when no credentials."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    assert profile_from_env_raw() is None


def test_profile_from_env_raw_picks_up_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env raw picks up version."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "t")
    monkeypatch.setenv("DHIS2_VERSION", "v43")
    profile = profile_from_env_raw()
    assert profile is not None
    assert profile.version == Dhis2.V43


def test_validate_profile_name_accepts_valid_names() -> None:
    """Validate profile name accepts valid names."""
    for name in ("local", "prod", "prod_eu", "test42", "Abc123"):
        assert validate_profile_name(name) == name


def test_validate_profile_name_rejects_empty() -> None:
    """Validate profile name rejects empty."""
    with pytest.raises(InvalidProfileNameError):
        validate_profile_name("")


def test_validate_profile_name_rejects_leading_digit() -> None:
    """Validate profile name rejects leading digit."""
    with pytest.raises(InvalidProfileNameError):
        validate_profile_name("1prod")


def test_validate_profile_name_rejects_overlong() -> None:
    """Validate profile name rejects overlong."""
    with pytest.raises(InvalidProfileNameError):
        validate_profile_name("a" * (PROFILE_NAME_MAX_LEN + 1))
