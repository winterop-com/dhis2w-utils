"""Unit tests for profile-name validation."""

from __future__ import annotations

import pytest
from dhis2w_core.profile import InvalidProfileNameError, validate_profile_name


@pytest.mark.parametrize(
    "name",
    [
        "local",
        "prod",
        "prod_eu",
        "test42",
        "laohis42",
        "a",
        "A_B_C_123",
        "x" * 64,
    ],
)
def test_valid_names(name: str) -> None:
    """Valid names."""
    assert validate_profile_name(name) == name


@pytest.mark.parametrize(
    "bad",
    [
        "",
        " ",
        "he llo",
        "prod-eu",
        "with.dot",
        "1starts_with_digit",
        "_starts_with_underscore",
        "has slash/bad",
        "with\ttab",
        "with\nnewline",
        "x" * 65,
    ],
)
def test_invalid_names_raise(bad: str) -> None:
    """Invalid names raise."""
    with pytest.raises(InvalidProfileNameError):
        validate_profile_name(bad)


def test_error_mentions_the_bad_name(capfd: pytest.CaptureFixture[str]) -> None:
    """Error mentions the bad name."""
    try:
        validate_profile_name("he llo")
    except InvalidProfileNameError as exc:
        assert "he llo" in str(exc)
        assert "letter" in str(exc).lower()
    else:  # pragma: no cover — defensive branch
        raise AssertionError("expected InvalidProfileNameError")
