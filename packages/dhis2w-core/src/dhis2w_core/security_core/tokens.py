"""Personal access token (PAT) inventory: non-expiring tokens, missing IP allowlists, account scope.

A DHIS2 Personal Access Token is a standing credential that authenticates API calls without an
interactive login and without 2FA: a leaked long-lived PAT grants the full authority set of its owning
user until it is manually revoked. The check inventories the tokens readable by the audited account via
GET `/api/apiToken` and flags weak posture: tokens with no expiry (HIGH, a live permanent credential),
tokens already expired but never deleted (WARN, inert stale state), tokens with no IP allowlist, and the
worst case of a never-expiring token with no IP allowlist.

Scope is a runtime authority distinction, not a version one. `ApiToken` is `defaultPrivate(true)` and the
list goes through the ACL-aware store filtered by `createdBy` ownership, so a non-superuser sees only its
OWN tokens; only an account with the ALL authority (superuser, which bypasses the ACL) gets the
system-wide inventory. Every finding is therefore scoped to "tokens readable by the audited account", and
a non-superuser run emits an INFO caveat that it cannot prove the absence of dangerous PATs owned by other
users.

The token secret (`key`) is `@JsonIgnore` upstream and never serialised over the wire, so no secret-like
field is ever read or carried: `TokenView` holds only the non-secret identity, type, expiry, owner id, and
the allowlist constraints. Determinism: the expired-but-not-deleted detection compares each token's expiry
to a `now` reference passed in by the caller, so the reducer never reads the clock and stays unit-testable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.controls import CheckOutcome, ControlLog
from dhis2w_core.security_core.findings import AuditFinding, Severity

_CHECK = "tokens"

# The verbatim scope sentence every account-scoped token finding must state, so a reader of a single
# finding knows the inventory is bounded by the audited account's ACL reach.
_SCOPE_SENTENCE = (
    "account-scoped: a non-superuser sees only its own tokens; a full system inventory requires an "
    "account with ALL authority."
)


class TokenAllowlists(BaseModel):
    """The IP / method / referer constraints flattened from a token's polymorphic attributes list."""

    model_config = ConfigDict(frozen=True)

    ips: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    referrers: tuple[str, ...] = ()


class TokenView(BaseModel):
    """One personal access token reduced to the non-secret fields the tokens audit reasons over."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str | None = None
    token_type: str
    expire_epoch_millis: int | None = None
    created: str | None = None
    owner_id: str | None = None
    allowlists: TokenAllowlists = TokenAllowlists()


class TokensInventory(BaseModel):
    """The tokens readable by the audited account plus whether that account holds the ALL authority."""

    model_config = ConfigDict(frozen=True)

    tokens: tuple[TokenView, ...] = ()
    account_is_superuser: bool = False


def evaluate_tokens(inventory: TokensInventory, *, now_epoch_millis: int) -> CheckOutcome:
    """Record the PAT controls (inventory, non-expiring, expired-not-deleted, no-IP-allowlist) plus scope.

    `now_epoch_millis` is the reference time the expired-but-not-deleted detection compares each token's
    expiry against; the caller (the I/O-edge runner) supplies it so this reducer stays deterministic and
    never reads the clock.
    """
    log = ControlLog(_CHECK)
    log.mark_passed("tokens-non-expiring", "tokens-expired-not-deleted", "tokens-no-ip-allowlist")
    if inventory.tokens:
        log.record(_inventory_finding(inventory))
    else:
        log.mark_passed("tokens-inventory")
    for token in inventory.tokens:
        for finding in _token_findings(token, now_epoch_millis=now_epoch_millis):
            log.record(finding)
    if not inventory.account_is_superuser:
        log.record(_degraded_account_scoped_finding())
    return log.result()


def _token_findings(token: TokenView, *, now_epoch_millis: int) -> list[AuditFinding]:
    """Per-token findings: non-expiring OR expired-but-undeleted, and a missing IP allowlist.

    The two expiry states are distinct verdicts: a token with no expiry is a live permanent credential
    (HIGH); a token whose expiry has already passed is inert (DHIS2 rejects it server-side) and only a
    hygiene cleanup item (WARN). The no-IP-allowlist worst case combines only with the live
    never-expiring state, never with an inert expired token.
    """
    findings: list[AuditFinding] = []
    non_expiring = token.expire_epoch_millis is None
    expired = token.expire_epoch_millis is not None and token.expire_epoch_millis < now_epoch_millis
    no_ip_allowlist = not token.allowlists.ips
    if non_expiring:
        findings.append(_non_expiring_finding(token))
    elif expired:
        findings.append(_expired_not_deleted_finding(token, now_epoch_millis=now_epoch_millis))
    if no_ip_allowlist:
        findings.append(_no_ip_allowlist_finding(token, worst_case=non_expiring))
    return findings


def _inventory_finding(inventory: TokensInventory) -> AuditFinding:
    """Summarise the PATs visible to the audited account, stating the account-scoped scope verbatim."""
    tokens = inventory.tokens
    never = sum(1 for token in tokens if token.expire_epoch_millis is None)
    no_ip = sum(1 for token in tokens if not token.allowlists.ips)
    with_method = sum(1 for token in tokens if token.allowlists.methods)
    with_referer = sum(1 for token in tokens if token.allowlists.referrers)
    types = sorted({token.token_type for token in tokens})
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Personal access token inventory",
        detail=(
            f"{len(tokens)} personal access token(s) visible to the audited account "
            f"(types: {', '.join(types) or 'unknown'}); {never} never expire, {no_ip} have no IP "
            f"allowlist, {with_method} carry a method allowlist, {with_referer} carry a referer "
            f"allowlist. Each PAT bypasses interactive login and 2FA and inherits its owner's full "
            f"authority set. This inventory is {_SCOPE_SENTENCE}"
        ),
        group_key="tokens-inventory",
        evidence={
            "total": str(len(tokens)),
            "never_expire": str(never),
            "no_ip_allowlist": str(no_ip),
            "with_method_allowlist": str(with_method),
            "with_referer_allowlist": str(with_referer),
        },
        control="tokens-inventory",
    )


def _non_expiring_finding(token: TokenView) -> AuditFinding:
    """Flag a token that never expires: a live permanent credential."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Non-expiring personal access token",
        detail=(
            f"Token '{token.name or token.id}' (type {token.token_type}) has no expiry. A token with no "
            "expiry is a permanent credential; if it leaks it grants standing API access until manually "
            "revoked. Within readable scope only."
        ),
        subject=token.name or token.id,
        group_key="tokens-non-expiring",
        evidence={
            "token": token.name or token.id,
            "type": token.token_type,
            "expires": "never",
            "created": token.created or "unknown",
        },
        control="tokens-non-expiring",
    )


def _expired_not_deleted_finding(token: TokenView, *, now_epoch_millis: int) -> AuditFinding:
    """Flag a token whose expiry has passed but which was never deleted: inert, but stale-state hygiene.

    DHIS2 rejects an expired token server-side, so this is NOT a live credential; the risk is limited
    to inventory clutter and the signal that token lifecycle cleanup is not happening. WARN, not HIGH.
    """
    expiry = _expiry_text(token, now_epoch_millis=now_epoch_millis)
    return AuditFinding(
        check=_CHECK,
        severity=Severity.WARN,
        title="Expired personal access token not deleted",
        detail=(
            f"Token '{token.name or token.id}' (type {token.token_type}) {expiry}. An expired token is "
            "rejected by DHIS2 and grants no access, but leaving it undeleted clutters the inventory and "
            "suggests token lifecycle cleanup is not happening. Delete it. Within readable scope only."
        ),
        subject=token.name or token.id,
        group_key="tokens-expired-not-deleted",
        evidence={
            "token": token.name or token.id,
            "type": token.token_type,
            "expires": expiry,
            "created": token.created or "unknown",
        },
        control="tokens-expired-not-deleted",
    )


def _no_ip_allowlist_finding(token: TokenView, *, worst_case: bool) -> AuditFinding:
    """Flag a token with no IP allowlist; calls out the worst case when it also never expires."""
    worst = (
        " This token also never expires: a token that never expires AND has no IP allowlist is the worst "
        "case: a permanent credential usable from anywhere."
        if worst_case
        else ""
    )
    return AuditFinding(
        check=_CHECK,
        severity=Severity.HIGH,
        title="Personal access token with no IP allowlist",
        detail=(
            f"Token '{token.name or token.id}' (type {token.token_type}) has no IP allowlist, so it is "
            f"usable from any source address.{worst} Within readable scope only."
        ),
        subject=token.name or token.id,
        group_key="tokens-no-ip-allowlist",
        evidence={"token": token.name or token.id, "type": token.token_type, "ip_allowlist": "none"},
        control="tokens-no-ip-allowlist",
    )


def _degraded_account_scoped_finding() -> AuditFinding:
    """INFO caveat that the inventory is account-scoped, so other users' tokens are invisible to this scan."""
    return AuditFinding(
        check=_CHECK,
        severity=Severity.INFO,
        title="Token inventory is account-scoped",
        detail=(
            "The audited account does not hold the ALL authority, so the token inventory is "
            f"{_SCOPE_SENTENCE} Tokens owned by other users are invisible to this scan; their absence "
            "from the report is not proof they do not exist."
        ),
        group_key="tokens-degraded-account-scoped",
        evidence={"account_is_superuser": "false"},
    )


def _expiry_text(token: TokenView, *, now_epoch_millis: int) -> str:
    """Render the human expiry phrase: 'expires: never' or the past date for an expired-but-live token."""
    if token.expire_epoch_millis is None:
        return "expires: never"
    moment = datetime.fromtimestamp(token.expire_epoch_millis / 1000, tz=UTC)
    return f"expired on {moment.date().isoformat()} but was not deleted"
