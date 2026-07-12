"""CliRunner tests for `d2w profile remove` confirmation gating."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point config paths at tmp_path so tests never touch the user's real profiles."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    yield


def test_profile_remove_confirm_accept() -> None:
    """Answering `y` at the prompt proceeds to remove the profile."""
    remove = MagicMock(return_value=Path("/tmp/profiles.toml"))
    with patch("dhis2w_core.v42.plugins.profile.service.remove_profile", new=remove):
        result = CliRunner().invoke(build_app(), ["profile", "remove", "stale"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "removed 'stale'" in result.output
    remove.assert_called_once()


def test_profile_remove_confirm_abort_skips_service() -> None:
    """Answering `n` aborts before removal; the credential-loss warning is shown."""
    remove = MagicMock()
    with patch("dhis2w_core.v42.plugins.profile.service.remove_profile", new=remove):
        result = CliRunner().invoke(build_app(), ["profile", "remove", "stale"], input="n\n")
    assert result.exit_code != 0
    assert "cannot be recovered" in result.output
    remove.assert_not_called()


def test_profile_remove_yes_flag_skips_prompt() -> None:
    """`--yes` removes without prompting."""
    remove = MagicMock(return_value=Path("/tmp/profiles.toml"))
    with patch("dhis2w_core.v42.plugins.profile.service.remove_profile", new=remove):
        result = CliRunner().invoke(build_app(), ["profile", "remove", "stale", "--yes"])
    assert result.exit_code == 0, result.output
    assert "removed 'stale'" in result.output
    remove.assert_called_once()
