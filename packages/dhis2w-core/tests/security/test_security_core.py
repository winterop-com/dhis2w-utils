"""Unit tests for the shared security core (authority taxonomy, severity model)."""

from __future__ import annotations

from dhis2w_core.security_core import (
    AUTHORITY_CATEGORIES,
    SEVERITY_ORDER,
    Severity,
    build_account_authorities,
    categorise_authorities,
    role_severity,
    severity_rank,
)

# ----- categorise_authorities -----


def test_categorise_returns_superuser_for_all() -> None:
    """`ALL` lands in the dedicated superuser bucket and nothing else."""
    cats = categorise_authorities({"ALL"})
    assert [c.key for c in cats] == ["superuser"]


def test_categorise_returns_every_overlapping_category() -> None:
    """A role with mixed admin auths should land in multiple categories."""
    cats = categorise_authorities({"F_INSERT_CUSTOM_JS_CSS", "F_SYSTEM_SETTING", "F_VIEW_UNRELATED"})
    keys = {c.key for c in cats}
    assert "app_management" in keys
    assert "system_settings" in keys
    # An unknown F_* string must not invent a category.
    assert "view_unrelated" not in keys


def test_categorise_preserves_severity_order() -> None:
    """Categories come back in AUTHORITY_CATEGORIES order so renderers can rely on it."""
    auths = {"F_SCHEDULING_ADMIN", "ALL", "F_INSERT_CUSTOM_JS_CSS"}
    keys = [c.key for c in categorise_authorities(auths)]
    assert keys == ["superuser", "app_management", "data_admin"]


def test_categorise_empty_input_returns_empty_list() -> None:
    """No authorities, no categories."""
    assert categorise_authorities(set()) == []


def test_authority_categories_have_unique_keys() -> None:
    """Renderers index by `.key`; a duplicate would silently drop categories."""
    keys = [c.key for c in AUTHORITY_CATEGORIES]
    assert len(keys) == len(set(keys))


def test_impersonate_user_maps_to_user_management() -> None:
    """F_IMPERSONATE_USER (account takeover) is a user-management dangerous authority."""
    assert [c.key for c in categorise_authorities({"F_IMPERSONATE_USER"})] == ["user_management"]


def test_public_route_maps_to_route_management() -> None:
    """F_ROUTE_PUBLIC_ADD (SSRF-relay creation) is a route-management dangerous authority."""
    assert [c.key for c in categorise_authorities({"F_ROUTE_PUBLIC_ADD"})] == ["route_management"]


def test_system_setting_maps_to_system_settings() -> None:
    """F_SYSTEM_SETTING already maps to the system-configuration category."""
    assert [c.key for c in categorise_authorities({"F_SYSTEM_SETTING"})] == ["system_settings"]


# ----- build_account_authorities -----


def test_build_account_authorities_sorts_and_dedupes() -> None:
    """Input order and duplicates never leak into the typed summary."""
    account = build_account_authorities(["F_USER_ADD", "F_INSERT_CUSTOM_JS_CSS", "F_USER_ADD"])
    assert account.authorities == ["F_INSERT_CUSTOM_JS_CSS", "F_USER_ADD"]
    assert account.is_superuser is False


def test_build_account_authorities_flags_superuser() -> None:
    """`ALL` sets the superuser flag and matches only the superuser category."""
    account = build_account_authorities(["ALL"])
    assert account.is_superuser is True
    assert [match.key for match in account.categories] == ["superuser"]
    assert account.categories[0].matched == ["ALL"]


def test_build_account_authorities_matched_is_per_category_subset() -> None:
    """Each category match carries exactly the held authorities that triggered it."""
    account = build_account_authorities(["F_USER_ADD", "F_USER_DELETE", "F_SQLVIEW_PUBLIC_ADD", "F_HARMLESS"])
    by_key = {match.key: match for match in account.categories}
    assert by_key["user_management"].matched == ["F_USER_ADD", "F_USER_DELETE"]
    assert by_key["sql_views"].matched == ["F_SQLVIEW_PUBLIC_ADD"]
    assert set(by_key) == {"user_management", "sql_views"}


def test_build_account_authorities_empty_input() -> None:
    """An account with no authorities yields the empty, non-superuser summary."""
    account = build_account_authorities([])
    assert account.authorities == []
    assert account.is_superuser is False
    assert account.categories == []


# ----- severity model -----


def test_severity_rank_matches_order() -> None:
    """`severity_rank` is the index into SEVERITY_ORDER, CRITICAL first."""
    ranks = [severity_rank(severity) for severity in SEVERITY_ORDER]
    assert ranks == sorted(ranks)
    assert severity_rank(Severity.CRITICAL) == 0
    assert severity_rank(Severity.INFO) == len(SEVERITY_ORDER) - 1


def test_role_severity_tiers() -> None:
    """ALL is CRITICAL; high-impact categories HIGH; the rest MEDIUM."""
    assert role_severity(["superuser"], has_all=True) is Severity.CRITICAL
    assert role_severity([], has_all=True) is Severity.CRITICAL
    assert role_severity(["sql_views"], has_all=False) is Severity.HIGH
    assert role_severity(["tracker_admin"], has_all=False) is Severity.MEDIUM
