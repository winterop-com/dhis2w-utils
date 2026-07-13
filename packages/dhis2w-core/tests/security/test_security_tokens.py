"""Tokens-check tests: PAT inventory, non-expiring / no-IP-allowlist findings, account scope, and wiring.

`evaluate_tokens` is version-invariant and tested directly with hand-built `TokensInventory` inputs; the
expired-but-not-deleted path is exercised with a fixed `now_epoch_millis` so it stays deterministic. The
`_run_tokens` wiring (which reads `/api/me/authorization` for the ALL flag, lists `/api/apiToken` via
`get_raw`, wraps the payload through the per-tree `_wire.tokens_from_raw` extractor, and reduces it) is
exercised against a mock client across all three version trees, covering the v41 `Literal`-type vs
v42/v43 enum-type normalization, the polymorphic attributes flattening, and asserting that no token secret
(`key`) ever surfaces in a TokenView or finding.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from dhis2w_client.errors import Dhis2ApiError
from dhis2w_core.security_core import (
    CheckStatus,
    Severity,
    TokenAllowlists,
    TokensInventory,
    TokenView,
    evaluate_tokens,
)

TREES = ("v41", "v42", "v43")

# A fixed reference clock so the expired-but-not-deleted detection is deterministic: 2026-06-24T00:00:00Z.
_NOW_EPOCH_MILLIS = 1782259200000
# One day before _NOW: an expiry epoch already in the past.
_PAST_EPOCH_MILLIS = _NOW_EPOCH_MILLIS - 86_400_000
# One year after _NOW: a healthy future expiry.
_FUTURE_EPOCH_MILLIS = _NOW_EPOCH_MILLIS + 31_536_000_000

# A well-formed token: future expiry and an IP allowlist, so it raises no per-token finding.
_HEALTHY = TokenView(
    id="tok000000001",
    name="ci-token",
    token_type="PERSONAL_ACCESS_TOKEN_V2",
    expire_epoch_millis=_FUTURE_EPOCH_MILLIS,
    created="2026-01-01T00:00:00",
    owner_id="user00000001",
    allowlists=TokenAllowlists(ips=("10.0.0.0/8",), methods=("GET",), referrers=()),
)


def _titles(findings: list[Any]) -> set[str]:
    """Collect finding titles for membership assertions."""
    return {finding.title for finding in findings}


def _by_title(findings: list[Any]) -> dict[str, Any]:
    """Index findings by title for severity/detail assertions."""
    return {finding.title: finding for finding in findings}


# ---------------------------------------------------------------------------
# evaluate_tokens (version-invariant)
# ---------------------------------------------------------------------------


def test_empty_inventory_superuser_emits_nothing() -> None:
    """A superuser with no readable tokens emits no findings at all (no inventory, no scope caveat)."""
    inventory = TokensInventory(tokens=(), account_is_superuser=True)
    assert evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings == []


def test_empty_inventory_non_superuser_emits_only_scope_caveat() -> None:
    """A non-superuser with no readable tokens still emits the INFO account-scoped caveat."""
    inventory = TokensInventory(tokens=(), account_is_superuser=False)
    findings = evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings
    assert _titles(findings) == {"Token inventory is account-scoped"}
    assert _by_title(findings)["Token inventory is account-scoped"].severity is Severity.INFO


def test_healthy_token_superuser_emits_only_inventory() -> None:
    """A healthy token under a superuser yields only the MEDIUM inventory finding."""
    inventory = TokensInventory(tokens=(_HEALTHY,), account_is_superuser=True)
    findings = evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings
    assert _titles(findings) == {"Personal access token inventory"}
    assert _by_title(findings)["Personal access token inventory"].severity is Severity.MEDIUM


def test_inventory_detail_states_scope_sentence_verbatim() -> None:
    """The inventory finding detail states the verbatim account-scoped scope sentence."""
    inventory = TokensInventory(tokens=(_HEALTHY,), account_is_superuser=True)
    finding = _by_title(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)[
        "Personal access token inventory"
    ]
    assert (
        "account-scoped: a non-superuser sees only its own tokens; a full system inventory requires an "
        "account with ALL authority." in finding.detail
    )


def test_non_expiring_null_expire_is_high() -> None:
    """A token with no expiry (null) flags the HIGH non-expiring finding with 'expires: never'."""
    token = _HEALTHY.model_copy(update={"expire_epoch_millis": None})
    inventory = TokensInventory(tokens=(token,), account_is_superuser=True)
    finding = _by_title(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)[
        "Non-expiring personal access token"
    ]
    assert finding.severity is Severity.HIGH
    assert (finding.evidence or {})["expires"] == "expires: never"


def test_non_expiring_past_epoch_is_high_deterministic() -> None:
    """A token whose expiry epoch is already in the past flags the HIGH non-expiring finding (fixed now)."""
    token = _HEALTHY.model_copy(update={"expire_epoch_millis": _PAST_EPOCH_MILLIS})
    inventory = TokensInventory(tokens=(token,), account_is_superuser=True)
    finding = _by_title(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)[
        "Non-expiring personal access token"
    ]
    assert finding.severity is Severity.HIGH
    assert "expired on 2026-06-23" in (finding.evidence or {})["expires"]


def test_future_expiry_does_not_flag_non_expiring() -> None:
    """A token with a future expiry is not flagged as non-expiring."""
    inventory = TokensInventory(tokens=(_HEALTHY,), account_is_superuser=True)
    assert "Non-expiring personal access token" not in _titles(
        evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings
    )


def test_no_ip_allowlist_is_high() -> None:
    """A token with an empty IP allowlist flags the HIGH no-IP-allowlist finding."""
    token = _HEALTHY.model_copy(update={"allowlists": TokenAllowlists(ips=(), methods=("GET",))})
    inventory = TokensInventory(tokens=(token,), account_is_superuser=True)
    finding = _by_title(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)[
        "Personal access token with no IP allowlist"
    ]
    assert finding.severity is Severity.HIGH
    assert (finding.evidence or {})["ip_allowlist"] == "none"


def test_worst_case_non_expiring_and_no_ip_allowlist_is_called_out() -> None:
    """A token that never expires AND has no IP allowlist fires both HIGHs and calls out the worst case."""
    token = _HEALTHY.model_copy(update={"expire_epoch_millis": None, "allowlists": TokenAllowlists()})
    inventory = TokensInventory(tokens=(token,), account_is_superuser=True)
    findings = evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings
    titles = _titles(findings)
    assert "Non-expiring personal access token" in titles
    assert "Personal access token with no IP allowlist" in titles
    no_ip = _by_title(findings)["Personal access token with no IP allowlist"]
    assert "worst case" in no_ip.detail


def test_no_ip_allowlist_with_future_expiry_does_not_call_out_worst_case() -> None:
    """A token missing only the IP allowlist (but with a future expiry) does not mention the worst case."""
    token = _HEALTHY.model_copy(update={"allowlists": TokenAllowlists()})
    inventory = TokensInventory(tokens=(token,), account_is_superuser=True)
    no_ip = _by_title(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)[
        "Personal access token with no IP allowlist"
    ]
    assert "worst case" not in no_ip.detail


def test_non_expiring_finding_evidence_includes_created() -> None:
    """The non-expiring finding carries a 'created' key in evidence so the field is not dead weight."""
    token = _HEALTHY.model_copy(update={"expire_epoch_millis": None})
    inventory = TokensInventory(tokens=(token,), account_is_superuser=True)
    finding = _by_title(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)[
        "Non-expiring personal access token"
    ]
    assert "created" in (finding.evidence or {})
    assert (finding.evidence or {})["created"] == "2026-01-01T00:00:00"


def test_non_superuser_with_tokens_adds_scope_caveat() -> None:
    """A non-superuser run with a token emits the inventory plus the INFO account-scoped caveat."""
    inventory = TokensInventory(tokens=(_HEALTHY,), account_is_superuser=False)
    titles = _titles(evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings)
    assert "Personal access token inventory" in titles
    assert "Token inventory is account-scoped" in titles


def test_superuser_with_tokens_omits_scope_caveat() -> None:
    """A superuser run never emits the account-scoped INFO caveat."""
    inventory = TokensInventory(tokens=(_HEALTHY,), account_is_superuser=True)
    assert "Token inventory is account-scoped" not in _titles(
        evaluate_tokens(inventory, now_epoch_millis=_NOW_EPOCH_MILLIS).findings
    )


# ---------------------------------------------------------------------------
# Per-tree wiring: _run_tokens reads /api/apiToken + /api/me/authorization
# ---------------------------------------------------------------------------


def _audit_module(tree: str) -> ModuleType:
    """Import the per-tree security audit module under test."""
    return import_module(f"dhis2w_core.{tree}.plugins.security.audit")


def _mock_client(*, tokens: list[dict[str, Any]], authorities: list[str]) -> MagicMock:
    """A client whose get_raw routes /api/apiToken and /api/me/authorization to canned payloads."""

    async def _get_raw(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/api/apiToken":
            return {"apiToken": tokens}
        if path == "/api/me/authorization":
            return {"data": authorities}
        raise AssertionError(f"unexpected path: {path}")

    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=_get_raw)
    return client


def _token_type_for(tree: str) -> str:
    """The wire `type` value used per tree: v41 carries a Literal string, v42/v43 the enum value (same str)."""
    return "PERSONAL_ACCESS_TOKEN_V2"


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_flags_non_expiring_no_ip_token(tree: str) -> None:
    """A token with no expiry and no IP allowlist flags both HIGHs and never leaks a secret-like field."""
    token: dict[str, Any] = {
        "id": "tok000000001",
        "name": "long-lived",
        "type": _token_type_for(tree),
        "expire": None,
        "created": "2026-01-01T00:00:00.000",
        "createdBy": {"id": "user00000001"},
        "attributes": [],
        # A `key` must never be on the wire; include one to prove it is never read or carried.
        "key": "do-not-leak-secret",
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["ALL"]))

    assert result.status is CheckStatus.OK
    titles = _titles(result.findings)
    assert "Personal access token inventory" in titles
    assert "Non-expiring personal access token" in titles
    assert "Personal access token with no IP allowlist" in titles
    assert "do-not-leak-secret" not in repr(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_flattens_ip_allowlist_attribute(tree: str) -> None:
    """An IpAllowedList attribute is flattened so a token with allowed IPs raises no no-IP finding."""
    token = {
        "id": "tok000000002",
        "name": "scoped",
        "type": _token_type_for(tree),
        "expire": _FUTURE_EPOCH_MILLIS,
        "createdBy": {"id": "user00000001"},
        "attributes": [
            {"type": "IpAllowedList", "allowedIps": ["192.168.0.0/16"]},
            {"type": "MethodAllowedList", "allowedMethods": ["GET", "POST"]},
            {"type": "RefererAllowedList", "allowedReferrers": ["https://app.example"]},
        ],
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["ALL"]))

    titles = _titles(result.findings)
    assert "Personal access token with no IP allowlist" not in titles
    assert "Non-expiring personal access token" not in titles
    inventory = _by_title(result.findings)["Personal access token inventory"]
    assert (inventory.evidence or {})["with_method_allowlist"] == "1"
    assert (inventory.evidence or {})["with_referer_allowlist"] == "1"
    assert (inventory.evidence or {})["no_ip_allowlist"] == "0"


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_normalizes_type_to_str(tree: str) -> None:
    """The token type is normalized to a plain str across v41 (Literal) and v42/v43 (enum) trees."""
    token = {
        "id": "tok000000003",
        "name": "typed",
        "type": _token_type_for(tree),
        "expire": _FUTURE_EPOCH_MILLIS,
        "createdBy": {"id": "user00000001"},
        "attributes": [{"type": "IpAllowedList", "allowedIps": ["10.0.0.0/8"]}],
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["ALL"]))

    inventory = _by_title(result.findings)["Personal access token inventory"]
    assert "PERSONAL_ACCESS_TOKEN_V2" in inventory.detail


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_non_superuser_emits_scope_caveat(tree: str) -> None:
    """A non-superuser account (no ALL authority) gets the INFO account-scoped caveat."""
    token = {
        "id": "tok000000004",
        "name": "mine",
        "type": _token_type_for(tree),
        "expire": _FUTURE_EPOCH_MILLIS,
        "createdBy": {"id": "user00000002"},
        "attributes": [{"type": "IpAllowedList", "allowedIps": ["10.0.0.0/8"]}],
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["F_USER_ADD"]))

    assert "Token inventory is account-scoped" in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_superuser_omits_scope_caveat(tree: str) -> None:
    """A superuser account (ALL authority present) does not get the account-scoped caveat."""
    token = {
        "id": "tok000000005",
        "name": "any",
        "type": _token_type_for(tree),
        "expire": _FUTURE_EPOCH_MILLIS,
        "createdBy": {"id": "user00000001"},
        "attributes": [{"type": "IpAllowedList", "allowedIps": ["10.0.0.0/8"]}],
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["ALL"]))

    assert "Token inventory is account-scoped" not in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_empty_inventory_superuser_is_clean(tree: str) -> None:
    """A superuser with no readable tokens yields an OK check with no findings."""
    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[], authorities=["ALL"]))

    assert result.status is CheckStatus.OK
    assert result.findings == []


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_never_carries_secret_field(tree: str) -> None:
    """No TokenView or finding ever carries a secret-like value even when the wire includes one."""
    token = {
        "id": "tok000000006",
        "name": "secretive",
        "type": _token_type_for(tree),
        "expire": _FUTURE_EPOCH_MILLIS,
        "createdBy": {"id": "user00000001"},
        "attributes": [{"type": "IpAllowedList", "allowedIps": ["10.0.0.0/8"]}],
        "key": "TOPSECRETKEY",
    }

    inventory = TokensInventory(
        tokens=tuple(_audit_module(tree)._wire.tokens_from_raw([token])),
        account_is_superuser=True,
    )

    assert "TOPSECRETKEY" not in repr(inventory)
    view = inventory.tokens[0]
    assert "key" not in view.model_dump()


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_degrades_on_api_error(tree: str) -> None:
    """A Dhis2ApiError reading /api/apiToken degrades the check with a note rather than passing clean."""

    async def _get_raw(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/api/me/authorization":
            return {"data": ["ALL"]}
        raise Dhis2ApiError(403, "forbidden")

    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=_get_raw)

    result = await _audit_module(tree)._run_tokens(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_degrades_on_transport_error(tree: str) -> None:
    """A transport error reading /api/apiToken degrades the check rather than reporting an empty inventory."""

    async def _get_raw(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/api/me/authorization":
            return {"data": ["ALL"]}
        raise httpx.ConnectError("boom")

    client = MagicMock()
    client.base_url = "https://mock.example"
    client.get_raw = AsyncMock(side_effect=_get_raw)

    result = await _audit_module(tree)._run_tokens(client)

    assert result.status is CheckStatus.DEGRADED
    assert result.findings == []
    assert result.note is not None and "HTTP error" in result.note


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_past_expiry_flags_non_expiring(tree: str) -> None:
    """A token whose expiry epoch is already in the past flags the non-expiring HIGH (expired-but-live)."""
    token = {
        "id": "tok000000007",
        "name": "stale",
        "type": _token_type_for(tree),
        "expire": _PAST_EPOCH_MILLIS,
        "createdBy": {"id": "user00000001"},
        "attributes": [{"type": "IpAllowedList", "allowedIps": ["10.0.0.0/8"]}],
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["ALL"]))

    assert "Non-expiring personal access token" in _titles(result.findings)


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_owner_id_matches_created_by(tree: str) -> None:
    """The parsed TokenView.owner_id equals createdBy.id from the wire payload (v41 id-only vs v42/v43 UserDto)."""
    token: dict[str, Any] = {
        "id": "tok000000008",
        "name": "owner-check",
        "type": _token_type_for(tree),
        "expire": _FUTURE_EPOCH_MILLIS,
        "createdBy": {"id": "user00000099"},
        "attributes": [{"type": "IpAllowedList", "allowedIps": ["10.0.0.0/8"]}],
    }

    views = _audit_module(tree)._wire.tokens_from_raw([token])

    assert len(views) == 1
    assert views[0].owner_id == "user00000099"


@pytest.mark.parametrize("tree", TREES)
async def test_run_tokens_non_expiring_finding_evidence_includes_created(tree: str) -> None:
    """The non-expiring finding evidence carries a 'created' key so the field is not dead."""
    token: dict[str, Any] = {
        "id": "tok000000009",
        "name": "evidence-check",
        "type": _token_type_for(tree),
        "expire": None,
        "created": "2026-01-15T10:00:00.000",
        "createdBy": {"id": "user00000001"},
        "attributes": [],
    }

    result = await _audit_module(tree)._run_tokens(_mock_client(tokens=[token], authorities=["ALL"]))

    non_expiring = _by_title(result.findings)["Non-expiring personal access token"]
    assert "created" in (non_expiring.evidence or {})
    assert (non_expiring.evidence or {})["created"] != "unknown"
