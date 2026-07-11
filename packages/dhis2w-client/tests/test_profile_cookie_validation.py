"""Tests for the `Profile.cookie` field validator — control-char and whitespace hygiene."""

from __future__ import annotations

import pytest
from dhis2w_client.profile import Profile
from pydantic import ValidationError


def test_cookie_none_is_allowed() -> None:
    """A profile without a session cookie leaves the optional field as None."""
    profile = Profile(base_url="https://play.dhis2.org", auth="pat", token="tok")
    assert profile.cookie is None


def test_cookie_single_pair_passes() -> None:
    """A plain `name=value` cookie is accepted verbatim."""
    profile = Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123")
    assert profile.cookie == "JSESSIONID=abc123"


def test_cookie_multi_pair_passes() -> None:
    """A multi-pair Cookie header with internal spaces and semicolons stays intact."""
    profile = Profile(base_url="https://play.dhis2.org", auth="session", cookie="A=1; B=2")
    assert profile.cookie == "A=1; B=2"


def test_cookie_surrounding_whitespace_is_stripped() -> None:
    """Leading and trailing whitespace is trimmed while the inner value is preserved."""
    profile = Profile(base_url="https://play.dhis2.org", auth="session", cookie="  JSESSIONID=abc123\n")
    assert profile.cookie == "JSESSIONID=abc123"


def test_cookie_with_embedded_newline_is_rejected() -> None:
    """An embedded newline (echo / clipboard artifact) fails validation with a control-char message."""
    with pytest.raises(ValidationError) as excinfo:
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=a\nb")
    assert "control characters" in str(excinfo.value)


def test_cookie_with_carriage_return_is_rejected() -> None:
    """An embedded carriage return is treated as a control character and rejected."""
    with pytest.raises(ValidationError):
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=a\rb")


def test_cookie_with_tab_is_rejected() -> None:
    """An embedded tab is a control character and is rejected."""
    with pytest.raises(ValidationError):
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=a\tb")


def test_cookie_whitespace_only_is_rejected() -> None:
    """A whitespace-only cookie is empty after trimming and is rejected."""
    with pytest.raises(ValidationError) as excinfo:
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="   ")
    assert "empty after trimming" in str(excinfo.value)
