"""Unit tests for dhis2w-core profile resolution via raw env vars."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_core.profile import NoProfileError, profile_from_env


def _clear_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate the test from real TOML + DHIS2_* env so only the explicitly-set vars apply."""
    for key in (
        "DHIS2_PROFILE",
        "DHIS2_URL",
        "DHIS2_PAT",
        "DHIS2_USERNAME",
        "DHIS2_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_profile_from_env_pat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env pat."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080/")
    monkeypatch.setenv("DHIS2_PAT", "d2p_test")
    profile = profile_from_env()
    assert profile.base_url == "http://localhost:8080"
    assert profile.auth == "pat"
    assert profile.token == "d2p_test"


def test_profile_from_env_basic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env basic."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_USERNAME", "admin")
    monkeypatch.setenv("DHIS2_PASSWORD", "district")
    profile = profile_from_env()
    assert profile.auth == "basic"
    assert profile.username == "admin"
    assert profile.password == "district"


def test_profile_from_env_pat_beats_basic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env pat beats basic."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    monkeypatch.setenv("DHIS2_PAT", "d2p_token")
    monkeypatch.setenv("DHIS2_USERNAME", "admin")
    monkeypatch.setenv("DHIS2_PASSWORD", "district")
    profile = profile_from_env()
    assert profile.auth == "pat"


def test_profile_from_env_missing_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env missing url."""
    _clear_env(monkeypatch, tmp_path)
    with pytest.raises(NoProfileError):
        profile_from_env()


def test_profile_from_env_missing_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Profile from env missing credentials."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DHIS2_URL", "http://localhost:8080")
    with pytest.raises(NoProfileError):
        profile_from_env()
