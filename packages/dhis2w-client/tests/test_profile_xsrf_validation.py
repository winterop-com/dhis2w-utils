"""Tests for the `Profile.xsrf_token` field validator — inert-by-default, control-char hygiene.

`xsrf_token` is optional: unlike `cookie`, an empty/whitespace-only value
normalizes to `None` (header omitted) instead of raising, so a stray
`DHIS2_SESSION_XSRF=""` behaves exactly like unset. A non-empty value carrying
control characters after trimming is still rejected, mirroring `cookie`.
"""

from __future__ import annotations

import pytest
from dhis2w_client.profile import Profile
from pydantic import ValidationError


def test_xsrf_none_is_allowed() -> None:
    """A session profile without a CSRF token leaves the optional field as None."""
    profile = Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123")
    assert profile.xsrf_token is None


def test_xsrf_plain_token_passes() -> None:
    """A plain token is accepted verbatim."""
    profile = Profile(
        base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="xsrf-tok-9"
    )
    assert profile.xsrf_token == "xsrf-tok-9"


def test_xsrf_empty_string_normalizes_to_none() -> None:
    """An empty token (e.g. DHIS2_SESSION_XSRF="") is inert — it normalizes to None, not "" ."""
    profile = Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="")
    assert profile.xsrf_token is None


def test_xsrf_whitespace_only_normalizes_to_none() -> None:
    """A whitespace-only token is empty after trimming and normalizes to None (header omitted)."""
    profile = Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="   ")
    assert profile.xsrf_token is None


def test_xsrf_surrounding_whitespace_is_stripped() -> None:
    """Leading and trailing whitespace is trimmed while the inner value is preserved."""
    profile = Profile(
        base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="  xsrf-tok-9\n"
    )
    assert profile.xsrf_token == "xsrf-tok-9"


def test_xsrf_with_embedded_newline_is_rejected() -> None:
    """An embedded newline (echo / clipboard artifact) fails with a control-char message."""
    with pytest.raises(ValidationError) as excinfo:
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="xsrf\ntok")
    assert "control characters" in str(excinfo.value)


def test_xsrf_with_carriage_return_is_rejected() -> None:
    """An embedded carriage return is treated as a control character and rejected."""
    with pytest.raises(ValidationError):
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="xsrf\rtok")


def test_xsrf_with_tab_is_rejected() -> None:
    """An embedded tab is a control character and is rejected."""
    with pytest.raises(ValidationError):
        Profile(base_url="https://play.dhis2.org", auth="session", cookie="JSESSIONID=abc123", xsrf_token="xsrf\ttok")
