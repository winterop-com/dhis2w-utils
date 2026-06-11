"""Dangerous-authority taxonomy and account-level categorisation.

DHIS2 ships ~250 ``F_*`` authority strings. Most are harmless data-entry
flags; a few dozen unlock capabilities an attacker (or a misconfigured
role) can chain into instance takeover. This module groups the riskiest
ones into named categories so every security check reports on them
consistently.

Categories are deliberately broad: better to over-flag than miss a sneak
path. Each category lists the authorities we treat as belonging to it.
The exact list is keyed to DHIS2 v41 to v43. ``categorise_authorities``
returns every category that overlaps with a role's authority set, so a
single matching member is enough to flag the category.

References:
- ``/api/schemas/authority`` on a live DHIS2 instance lists every known
  authority string for that version.
- The DHIS2 docs at docs.dhis2.org list the baseline set kept stable
  across versions.
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
# more authorities indirectly by editing roles and group memberships.
USER_MANAGEMENT = AuthorityCategory(
    key="user_management",
    label="User & role management",
    description="Provision accounts, edit user roles + groups. Privilege escalation by editing membership.",
    authorities=frozenset(
        {
            "F_USER_ADD",
            "F_USER_ADD_WITHIN_MANAGED_GROUP",
            "F_USER_DELETE",
            "F_USER_DELETE_WITHIN_MANAGED_GROUP",
            "F_USER_VIEW",
            "F_REPLICATE_USER",
            "F_USERROLE_PUBLIC_ADD",
            "F_USERROLE_PRIVATE_ADD",
            "F_USERROLE_DELETE",
            "F_USERGROUP_PUBLIC_ADD",
            "F_USERGROUP_PRIVATE_ADD",
            "F_USERGROUP_DELETE",
            "F_USERGROUP_MANAGING_RELATIONSHIPS_ADD",
            "F_USERGROUP_MANAGING_RELATIONSHIPS_VIEW",
        }
    ),
)

# App management lets you upload arbitrary frontend code that runs in
# every operator's browser session: XSS / token theft via a malicious
# app zip.
APP_MANAGEMENT = AuthorityCategory(
    key="app_management",
    label="App management",
    description="Install / remove DHIS2 apps. Upload of a malicious app zip yields persistent XSS for every operator.",
    authorities=frozenset({"F_APP_MANAGEMENT", "M_dhis-web-app-management"}),
)

# SQL views run as the DHIS2 server's database user; the right SELECTs
# can read tracker data wholesale, and DELETE/UPDATE views (rare but
# allowed) can mutate.
SQL_VIEWS = AuthorityCategory(
    key="sql_views",
    label="SQL views",
    description=(
        "Create / execute SQL views. Direct SELECT on tracker/data tables; some servers allow UPDATE/DELETE views."
    ),
    authorities=frozenset(
        {
            "F_SQLVIEW_PUBLIC_ADD",
            "F_SQLVIEW_PRIVATE_ADD",
            "F_SQLVIEW_DELETE",
            "F_SQLVIEW_EXECUTE",
            "F_SQLVIEW_EXTERNAL",
        }
    ),
)

# System settings include credential-bearing strings (SMTP / SMS provider
# keys, App Hub URL) and behavioural toggles (account self-registration).
SYSTEM_SETTINGS = AuthorityCategory(
    key="system_settings",
    label="System settings",
    description="Read / write system settings. Includes SMTP credentials, App Hub URL, self-registration toggles.",
    authorities=frozenset(
        {
            "F_SYSTEM_SETTING",
            "F_VIEW_UNBLOCKED_EMAIL_CONFIG",
            "F_VIEW_SERVER_INFO",
        }
    ),
)

# Metadata import/export is the cleanest path to exfiltrating an
# instance's data model (forms, programs, tracker config) and to
# back-dooring it (re-imported metadata can carry malicious app refs,
# scheduled jobs, etc.).
METADATA_IO = AuthorityCategory(
    key="metadata_io",
    label="Metadata import / export",
    description=(
        "Bulk metadata import + export. Wholesale exfiltration of the data model; re-import can carry back-doors."
    ),
    authorities=frozenset(
        {
            "F_METADATA_IMPORT",
            "F_METADATA_EXPORT",
            "F_EXPORT_DATA",
            "F_IMPORT_DATA",
            "F_EXPORT_EVENTS",
            "F_IMPORT_EVENTS",
        }
    ),
)

# Tracker admin overrides the org-unit sharing model: a tracker admin
# can read patient-level data outside their assigned units.
TRACKER_ADMIN = AuthorityCategory(
    key="tracker_admin",
    label="Tracker admin",
    description="View / search tracked entities outside the user's assigned org units. Overrides the sharing model.",
    authorities=frozenset(
        {
            "F_TRACKED_ENTITY_INSTANCE_SEARCH",
            "F_TRACKED_ENTITY_INSTANCE_SEARCH_IN_ALL_OU_GROUPS",
            "F_TRACKED_ENTITY_INSTANCE_VIEW_ALL_OU_GROUPS",
            "F_TRACKER_OWNERSHIP_OVERRIDE_NULL",
            "F_TRACKED_ENTITY_INSTANCE_MANAGEMENT",
        }
    ),
)

# Data administration covers maintenance jobs (analytics regen, db
# integrity checks) that run as the server user and can hide load.
DATA_ADMIN = AuthorityCategory(
    key="data_admin",
    label="Data administration",
    description="Server-side maintenance: analytics regen, integrity checks, approval levels.",
    authorities=frozenset(
        {
            "F_DATA_ADMINISTRATION",
            "F_PERFORM_MAINTENANCE",
            "F_DATA_APPROVAL_LEVEL",
            "F_RUN_SQL",
            "F_GENERATE_MIN_MAX_VALUES",
            "F_PREDICTOR_RUN",
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
