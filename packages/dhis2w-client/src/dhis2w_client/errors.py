"""Exception hierarchy for dhis2w-client — shared across all version trees.

Errors carry no version-specific behaviour, so they live in one module rather than being
copied per version. A single shared hierarchy means `except dhis2w_client.Dhis2ApiError`
catches errors from a client bound to *any* DHIS2 major (v41/v42/v43), not just the baseline.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dhis2w_client.v42.envelopes import WebMessageResponse

_WWW_AUTHENTICATE_DESCRIPTION_RE = re.compile(r'error_description\s*=\s*"([^"]*)"', re.IGNORECASE)
_OPENID_MAPPING_RE = re.compile(
    r"Found no matching DHIS2 user for the mapping claim:\s*'?(?P<claim>[^'\s]+)'?"
    r"\s*with the value:\s*'?(?P<value>[^']+?)'?\s*$",
)


def format_unauthorized_message(method: str, path: str, www_authenticate: str | None) -> str:
    """Build a 401 message, surfacing actionable hints for known DHIS2 OAuth2 failures."""
    base = f"401 Unauthorized at {method} {path}"
    if not www_authenticate:
        return base
    description_match = _WWW_AUTHENTICATE_DESCRIPTION_RE.search(www_authenticate)
    if description_match is None:
        return base
    description = description_match.group(1).strip()
    mapping_match = _OPENID_MAPPING_RE.search(description)
    if mapping_match:
        claim = mapping_match.group("claim")
        value = mapping_match.group("value")
        return (
            f"{base} — DHIS2 accepted the OAuth2 JWT but no DHIS2 user has "
            f"openId={value!r} set, so the OIDC mapping (claim={claim!r}) returned no match. "
            "As an admin, PATCH the target user once:\n"
            "  curl -u <admin>:<password> -X PATCH \\\n"
            "    -H 'Content-Type: application/json-patch+json' \\\n"
            f'    -d \'[{{"op":"add","path":"/openId","value":"{value}"}}]\' \\\n'
            "    <base_url>/api/users/<user-uid>\n"
            "Fixed in DHIS2 v43+."
        )
    return f"{base} — {description}"


class Dhis2ClientError(Exception):
    """Base class for all dhis2w-client errors."""


class Dhis2ApiError(Dhis2ClientError):
    """Raised when the DHIS2 API returns a non-success response."""

    def __init__(self, status_code: int, message: str, body: object | None = None) -> None:
        """Capture HTTP status, message, and optional response body."""
        super().__init__(f"DHIS2 API returned {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body

    @property
    def web_message(self) -> WebMessageResponse | None:
        """Parse `body` as a WebMessageResponse when the shape matches, else None.

        DHIS2 returns the envelope on errors too (e.g. 409 on /api/dataValueSets
        with `status=WARNING` + populated `conflicts[]`), so callers can inspect
        import counts and per-row rejections without re-parsing. The error-envelope
        shape is stable across majors, so the baseline (v42) model parses any tree's body.

        Imported lazily because `envelopes.py` pulls in the generated OAS tree,
        which itself imports `client.py` (for the generated resource
        accessors), and `client.py` imports `errors.py` — classic cycle. The
        `web_message` call-site runs only after the package is fully loaded,
        so the late import is safe.
        """
        if not isinstance(self.body, dict):
            return None
        from dhis2w_client.v42.envelopes import WebMessageResponse as _WMR

        try:
            return _WMR.model_validate(self.body)
        except Exception:
            return None


class AuthenticationError(Dhis2ClientError):
    """Raised when authentication fails or tokens are invalid."""


class OAuth2FlowError(Dhis2ClientError):
    """Raised when the OAuth 2.1 authorization-code flow fails."""


class UnsupportedVersionError(Dhis2ClientError):
    """Raised when the DHIS2 instance version has no generated client and fallback is disabled."""

    def __init__(self, version: str, available: list[str]) -> None:
        """Capture the reported version and the list of versions we have codegen for."""
        summary = ", ".join(available) if available else "none"
        super().__init__(
            f"DHIS2 instance reports version {version}; "
            f"no generated client available (have: {summary}). "
            "Run `dhis2 codegen --url <instance>` to generate one."
        )
        self.version = version
        self.available = available


class VersionPinMismatchError(UnsupportedVersionError):
    """Raised when `Dhis2Client(version=...)` pins a major different from the server's reported version."""

    def __init__(self, pinned: str, reported: str) -> None:
        """Capture the pinned generated tree + the wire-reported server version."""
        Dhis2ClientError.__init__(
            self,
            f"Dhis2Client pinned to {pinned!r} but DHIS2 reports {reported!r}. "
            "Running pinned-major models against a different-major server silently "
            "round-trips renamed or added fields wrong. Drop the explicit "
            "`version=` to auto-detect, or pass `allow_version_mismatch=True` if "
            "you've audited the schema overlap yourself.",
        )
        self.version = reported
        self.available = [pinned]
        self.pinned = pinned
        self.reported = reported
