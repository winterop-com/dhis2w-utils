"""Parse a local copy of DHIS2's `dhis.conf` into redaction-by-construction audit-posture models.

The DHIS2 audit configuration (the file logger, the database sink, the four per-scope matrices, and the
instance-wide enable flag) lives ONLY in `dhis.conf` via `ConfigurationKey.java`; none of it is a system
setting and none is exposed over `/api/configuration` or `/api/system/info`. There is therefore nothing
audit-related to read over the API, and `parse_dhis_conf` reads an explicit local path the operator points
at a copy of the file (the scanner never reads the server's filesystem).

Secret redaction is enforced by CONSTRUCTION, not discipline. The parser retains ONLY the `audit.*` keys
(as `AuditScopeMatrix`) plus a set/not-set `RedactedSecret(key, is_set)` for each confidential key;
`RedactedSecret` has no value field, so a secret value is physically unrepresentable through these models.
Non-audit, non-confidential keys are not represented at all.

The matrix strings are parsed exactly as `AuditMatrixConfigurer.java` does: semicolon-separated `AuditType`
names (CREATE / READ / UPDATE / DELETE / SEARCH / SECURITY). DHIS2 applies a built-in default of
{CREATE, UPDATE, DELETE, SECURITY} when a scope key is ABSENT or its value is an EMPTY string; an explicit
matrix overrides that default for that scope. The literal `DISABLED` token is a documented DHIS2 sentinel
that explicitly disables a scope (produces an empty type set), preserved in `parseAuditTypes` (~line 112 of
`AuditMatrixConfigurer.java`). Any other unrecognised token causes the DHIS2 server to throw
`IllegalArgumentException` at boot, so the instance would not start and we never encounter those in practice.

`audit.logger` defaults ON, `audit.database` OFF, and `system.audit.enabled` ON per `ConfigurationKey.java`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

# The four audit scopes (DHIS2 `AuditScope`) the per-scope matrix keys configure, paired with their
# `dhis.conf` key. METADATA / AGGREGATE / TRACKER / API.
_SCOPE_KEYS: tuple[tuple[str, str], ...] = (
    ("METADATA", "audit.metadata"),
    ("AGGREGATE", "audit.aggregate"),
    ("TRACKER", "audit.tracker"),
    ("API", "audit.api"),
)

# The valid DHIS2 `AuditType` members a scope matrix may list.
_VALID_AUDIT_TYPES: frozenset[str] = frozenset({"CREATE", "READ", "UPDATE", "DELETE", "SEARCH", "SECURITY"})

# DHIS2's `DEFAULT_AUDIT_CONFIGURATION` from `AuditMatrixConfigurer.java`: applied to any scope whose key
# is absent OR whose value is an empty string. An operator who sets an explicit matrix overrides this default.
_DEFAULT_AUDIT_TYPES: tuple[str, ...] = ("CREATE", "UPDATE", "DELETE", "SECURITY")

# The change-types every change-bearing scope should record for a forensic trail; a configured matrix that
# explicitly omits any of these is narrowly scoped relative to the DHIS2 default.
_FORENSIC_AUDIT_TYPES: tuple[str, ...] = ("CREATE", "UPDATE", "DELETE", "SECURITY")

# The confidential `dhis.conf` keys reported set/not-set only; their value is NEVER read into a model.
_CONFIDENTIAL_KEYS: tuple[str, ...] = (
    "encryption.password",
    "connection.password",
    "analytics.connection.password",
    "ldap.manager.password",
    "redis.password",
    "artemis.password",
    "oauth2.server.jwt.keystore.password",
    "oauth2.server.jwt.keystore.key-password",
    "system.monitoring.password",
)

# The semicolon separator DHIS2's `AuditMatrixConfigurer` splits a scope matrix string on.
_MATRIX_SEPARATOR = ";"

# The literal token DHIS2 treats as "disable this scope"; documented in `AuditMatrixConfigurer.java` ~line 112.
_DISABLED_TOKEN = "DISABLED"


class AuditScopeMatrix(BaseModel):
    """One audit scope's parsed matrix: the scope name, whether a matrix was explicitly set, and its effective types.

    `explicit` is True when the dhis.conf key was present with a non-empty value. When `explicit` is False,
    `audit_types` reflects the DHIS2 default {CREATE, UPDATE, DELETE, SECURITY}. When `explicit` is True and
    the matrix contains `DISABLED` or resolves to an empty set, `audit_types` is empty (scope disabled).
    """

    model_config = ConfigDict(frozen=True)

    scope: str
    explicit: bool
    audit_types: tuple[str, ...] = ()


class RedactedSecret(BaseModel):
    """A confidential `dhis.conf` key reduced to set/not-set; it cannot hold a secret value by construction."""

    model_config = ConfigDict(frozen=True)

    key: str
    is_set: bool


class AuditPosture(BaseModel):
    """The audit posture parsed from a `dhis.conf` copy, or the API-first (`parsed=False`) placeholder."""

    model_config = ConfigDict(frozen=True)

    system_enabled: bool | None = None
    logger_enabled: bool = True
    database_enabled: bool = False
    in_memory_queue_enabled: bool = False
    changelog_aggregate_enabled: bool = True
    scopes: tuple[AuditScopeMatrix, ...] = ()
    secrets: tuple[RedactedSecret, ...] = ()
    source_path: str | None = None
    parsed: bool = False


def parse_dhis_conf(path: Path) -> AuditPosture:
    """Parse a local `dhis.conf` copy into an `AuditPosture` with `parsed=True`.

    Raises `OSError` when the path is missing or unreadable and `ValueError` when the file has no readable
    key/value lines, so the I/O-edge runner maps either to a degraded note rather than a finding.
    """
    text = path.read_text(encoding="utf-8")
    values = _parse_properties(text)
    if not values:
        raise ValueError(f"no readable key=value lines in {path}")
    return _build_posture(values, source_path=str(path))


def _parse_properties(text: str) -> dict[str, str]:
    """Parse Java `.properties` text into a key->value map (handles `=`/`:` separators, `#`/`!` comments)."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        key, separator, value = _split_property(line)
        if not separator or not key:
            continue
        values[key] = value
    return values


def _split_property(line: str) -> tuple[str, str | None, str]:
    """Split one stripped `.properties` line into (key, separator, value); separator is None when absent."""
    equals = line.find("=")
    colon = line.find(":")
    index = _first_separator_index(equals, colon)
    if index is None:
        return line, None, ""
    return line[:index].strip(), line[index], line[index + 1 :].strip()


def _first_separator_index(equals: int, colon: int) -> int | None:
    """Return the index of the first `=` or `:` separator on the line, or None when neither is present."""
    candidates = [index for index in (equals, colon) if index != -1]
    return min(candidates) if candidates else None


def _build_posture(values: dict[str, str], *, source_path: str) -> AuditPosture:
    """Build the parsed `AuditPosture` from the raw key->value map, honouring the audit defaults."""
    return AuditPosture(
        system_enabled=_flag(values, "system.audit.enabled", default=True),
        logger_enabled=_flag(values, "audit.logger", default=True),
        database_enabled=_flag(values, "audit.database", default=False),
        in_memory_queue_enabled=_flag(values, "audit.in_memory-queue.enabled", default=False),
        changelog_aggregate_enabled=_flag(values, "changelog.aggregate", default=True),
        scopes=tuple(_scope_matrix(values, scope=scope, key=key) for scope, key in _SCOPE_KEYS),
        secrets=tuple(_redacted_secret(values, key) for key in _CONFIDENTIAL_KEYS),
        source_path=source_path,
        parsed=True,
    )


def _flag(values: dict[str, str], key: str, *, default: bool) -> bool:
    """Read an on/off `dhis.conf` flag (case-insensitive), falling back to its code default when absent."""
    raw = values.get(key)
    if raw is None:
        return default
    return raw.strip().lower() == "on"


def _scope_matrix(values: dict[str, str], *, scope: str, key: str) -> AuditScopeMatrix:
    """Parse one scope's matrix string into an `AuditScopeMatrix`, applying the DHIS2 default when absent/empty.

    When the key is absent OR its value is an empty string, DHIS2 applies DEFAULT_AUDIT_CONFIGURATION
    ({CREATE, UPDATE, DELETE, SECURITY}) and `explicit` is False. When the key is present with a non-empty
    value, `explicit` is True and `audit_types` holds the parsed set (which may be empty if DISABLED).
    """
    raw = values.get(key)
    if raw is None or not raw.strip():
        # Key absent or value blank: DHIS2 applies its built-in default.
        return AuditScopeMatrix(scope=scope, explicit=False, audit_types=_DEFAULT_AUDIT_TYPES)
    # Key present with a non-empty value: parse the explicit matrix (may result in empty if DISABLED).
    audit_types = _parse_matrix(raw)
    return AuditScopeMatrix(scope=scope, explicit=True, audit_types=audit_types)


def _parse_matrix(raw: str) -> tuple[str, ...]:
    """Parse a semicolon-separated matrix string into its valid `AuditType` tokens.

    The `DISABLED` token and blank tokens contribute no type, as documented in `AuditMatrixConfigurer.java`.
    Any other unrecognised token causes `IllegalArgumentException` at DHIS2 boot (instance won't start).
    """
    types: list[str] = []
    for token in raw.split(_MATRIX_SEPARATOR):
        trimmed = token.strip().upper()
        if not trimmed or trimmed == _DISABLED_TOKEN:
            continue
        if trimmed in _VALID_AUDIT_TYPES and trimmed not in types:
            types.append(trimmed)
    return tuple(types)


def _redacted_secret(values: dict[str, str], key: str) -> RedactedSecret:
    """Record a confidential key as set/not-set; a present non-blank value is `is_set=True`, never stored."""
    raw = values.get(key)
    is_set = raw is not None and bool(raw.strip())
    return RedactedSecret(key=key, is_set=is_set)
