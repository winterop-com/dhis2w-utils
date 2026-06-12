"""Unit tests for the clean CLI error rendering wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.cli_errors import run_app


def _clear_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_missing_profile_prints_clean_error_and_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Missing profile prints clean error and exits 1."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["d2w", "system", "whoami"])

    with pytest.raises(SystemExit) as exc_info:
        run_app(build_app())

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "error: no DHIS2 profile is configured" in err
    assert "d2w profile --help" in err
    assert "Traceback" not in err


def test_unknown_profile_prints_clean_error_and_exits_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Unknown profile prints clean error and exits 1."""
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["d2w", "--profile", "ghost", "system", "whoami"])

    with pytest.raises(SystemExit) as exc_info:
        run_app(build_app())

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no profile named 'ghost'" in err
    assert "d2w profile list" in err
    assert "Traceback" not in err
