"""Dangerous-authority taxonomy and account-level categorisation.

DHIS2 ships ~250 authority strings. Most are harmless data-entry flags; a
few dozen unlock capabilities an attacker (or a misconfigured role) can
chain into instance takeover. This module groups the riskiest ones into
named categories so every security check reports on them consistently.

Every string below is verified to exist in the live `/api/authorities`
inventory of both v42 and v43 (the contract test
`packages/dhis2w-core/tests/test_security_taxonomy_contract.py` enforces
this against the play instances). v41 cannot be verified the same way --
its `/api/authorities` endpoint returns 500 (BUGS.md #45).

Note on matching: `/api/me/authorization` reports *granted* strings, which
on long-lived databases can include residual names from older DHIS2
versions that the running server no longer defines (and therefore no
longer checks). The taxonomy deliberately keys on current-version names
only, so matches always describe capabilities the server enforces today.

References:
- ``GET /api/authorities`` on a live DHIS2 instance lists every authority
  string that version defines.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from dhis2w_core.security_core.models import AccountAuthorities, CategoryMatch


class AuthorityCategory(BaseModel):
    """One named risk category plus the authorities that put a role inside it."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    description: str
    authorities: frozenset[str]


# `ALL` short-circuits every other category, so it sits in its own bucket.
SUPERUSER = AuthorityCategory(
    key="superuser",
    label="Superuser (ALL)",
    description="Grants every authority. Instance-wide takeover.",
    authorities=frozenset({"ALL"}),
)

# Account / role provisioning. Anyone holding these can grant themselves
# more authorities indirectly by editing roles and group memberships, or
# directly by impersonating a more privileged account.
USER_MANAGEMENT = AuthorityCategory(
    key="user_management",
    label="User & role management",
    description=(
        "Provision accounts, edit user roles + groups, impersonate users. "
        "Privilege escalation by editing membership or switching identity."
    ),
    authorities=frozenset(
        {
            "F_USER_ADD",
            "F_USER_ADD_WITHIN_MANAGED_GROUP",
            "F_USER_DELETE",
            "F_USER_DELETE_WITHIN_MANAGED_GROUP",
            "F_USER_VIEW",
            "F_REPLICATE_USER",
            "F_IMPERSONATE_USER",
            "F_USERROLE_PUBLIC_ADD",
            "F_USERROLE_PRIVATE_ADD",
            "F_USERROLE_DELETE",
            "F_USERGROUP_PUBLIC_ADD",
            "F_USERGROUP_PRIVATE_ADD",
            "F_USERGROUP_DELETE",
        }
    ),
)

# App management and custom JS/CSS both let you ship arbitrary frontend
# code that runs in every operator's browser session: persistent XSS /
# token theft via a malicious app zip or an injected script block.
APP_MANAGEMENT = AuthorityCategory(
    key="app_management",
    label="App management & custom scripts",
    description=(
        "Install / remove DHIS2 apps or inject custom JS/CSS. Either yields persistent XSS for every operator session."
    ),
    authorities=frozenset({"M_dhis-web-app-management", "F_INSERT_CUSTOM_JS_CSS"}),
)

# SQL views run as the DHIS2 server's database user; the right SELECTs can
# read tracker data wholesale. Execution of an existing view is gated by
# the view's sharing, so authoring a view is the dangerous step.
SQL_VIEWS = AuthorityCategory(
    key="sql_views",
    label="SQL views",
    description="Author SQL views that run as the server's database user. Direct SELECT on tracker/data tables.",
    authorities=frozenset(
        {
            "F_SQLVIEW_PUBLIC_ADD",
            "F_SQLVIEW_PRIVATE_ADD",
            "F_SQLVIEW_DELETE",
        }
    ),
)

# System configuration includes credential-bearing strings (SMTP / SMS
# provider keys, App Hub URL), behavioural toggles (account
# self-registration), and OAuth2 client registration.
SYSTEM_SETTINGS = AuthorityCategory(
    key="system_settings",
    label="System configuration",
    description=(
        "Read / write system settings and register OAuth2 clients. "
        "Includes SMTP credentials, App Hub URL, self-registration toggles."
    ),
    authorities=frozenset(
        {
            "F_SYSTEM_SETTING",
            "F_VIEW_SERVER_INFO",
            "F_MOBILE_SETTINGS",
            "F_OAUTH2_CLIENT_MANAGE",
        }
    ),
)

# Metadata import/export is the cleanest path to exfiltrating an
# instance's data model (forms, programs, tracker config) and to
# back-dooring it (re-imported metadata can carry malicious app refs,
# scheduled jobs, etc.). Skipping the import audit hides the trail.
METADATA_IO = AuthorityCategory(
    key="metadata_io",
    label="Metadata import / export",
    description=(
        "Bulk metadata import + export. Wholesale exfiltration of the data model; "
        "re-import can carry back-doors; the audit-skip flag hides the trail."
    ),
    authorities=frozenset(
        {
            "F_METADATA_IMPORT",
            "F_METADATA_EXPORT",
            "F_EXPORT_DATA",
            "F_SKIP_DATA_IMPORT_AUDIT",
        }
    ),
)

# Tracker admin overrides the org-unit sharing model: cross-org-unit
# search reads patient-level data outside the user's assigned units, and
# merge destructively rewrites patient records.
TRACKER_ADMIN = AuthorityCategory(
    key="tracker_admin",
    label="Tracker admin",
    description=(
        "Search tracked entities across all org units (overrides the sharing model) "
        "and merge / rewrite patient-level records."
    ),
    authorities=frozenset(
        {
            "F_TRACKED_ENTITY_INSTANCE_SEARCH_IN_ALL_ORGUNITS",
            "F_TRACKED_ENTITY_MERGE",
        }
    ),
)

# Data administration covers maintenance jobs (analytics regen, integrity
# checks) and the job scheduler, which runs server-side tasks.
DATA_ADMIN = AuthorityCategory(
    key="data_admin",
    label="Data administration",
    description="Server-side maintenance and the job scheduler: analytics regen, integrity checks, scheduled tasks.",
    authorities=frozenset(
        {
            "F_PERFORM_MAINTENANCE",
            "F_DATA_APPROVAL_LEVEL",
            "F_GENERATE_MIN_MAX_VALUES",
            "F_PREDICTOR_RUN",
            "F_SCHEDULING_ADMIN",
        }
    ),
)


AUTHORITY_CATEGORIES: tuple[AuthorityCategory, ...] = (
    SUPERUSER,
    USER_MANAGEMENT,
    APP_MANAGEMENT,
    SQL_VIEWS,
    SYSTEM_SETTINGS,
    METADATA_IO,
    TRACKER_ADMIN,
    DATA_ADMIN,
)


def categorise_authorities(authorities: list[str] | set[str] | frozenset[str]) -> list[AuthorityCategory]:
    """Return every category whose authority set overlaps with the input.

    Categories are returned in :data:`AUTHORITY_CATEGORIES` order so
    renderers can rely on a stable display order. ``ALL`` does not
    suppress the other matches here; callers that want to collapse a
    superuser row decide that at the rendering layer.
    """
    auth_set = set(authorities)
    return [cat for cat in AUTHORITY_CATEGORIES if auth_set & cat.authorities]


def build_account_authorities(authorities: Iterable[str]) -> AccountAuthorities:
    """Categorise an account's effective authorities into the typed summary model."""
    names = sorted({str(authority) for authority in authorities})
    name_set = set(names)
    matches = [
        CategoryMatch(
            key=category.key,
            label=category.label,
            description=category.description,
            matched=sorted(name_set & category.authorities),
        )
        for category in categorise_authorities(names)
    ]
    return AccountAuthorities(
        authorities=names,
        is_superuser="ALL" in name_set,
        categories=matches,
    )
