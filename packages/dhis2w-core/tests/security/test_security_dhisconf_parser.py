"""Direct unit tests for the dhisconf.py parser trust boundary.

`_parse_properties`, `_split_property`, and `_parse_matrix` are the outermost trust boundary for the
redaction-by-construction contract: they produce the raw key->value map that `_build_posture` then converts
into typed models. Correctness here is the foundation for the redaction guarantee.

Tests cover: `=` and `:` separators, `#` and `!` comment forms, a confidential key whose value CONTAINS `=`
(is_set True, value never surfaced), duplicate-key last-wins, empty value, lowercase audit types, an
explicit narrow matrix, and the DISABLED sentinel.
"""

from __future__ import annotations

from pathlib import Path

from dhis2w_core.security_core.dhisconf import (
    _parse_matrix,
    _parse_properties,
    _split_property,
    parse_dhis_conf,
)

# ---------------------------------------------------------------------------
# _parse_properties
# ---------------------------------------------------------------------------


def test_parse_properties_equals_separator() -> None:
    """A key=value line is parsed correctly."""
    result = _parse_properties("audit.logger = on\n")
    assert result == {"audit.logger": "on"}


def test_parse_properties_colon_separator() -> None:
    """A key: value line (colon separator) is parsed correctly."""
    result = _parse_properties("audit.logger: on\n")
    assert result == {"audit.logger": "on"}


def test_parse_properties_hash_comment_ignored() -> None:
    """Lines starting with `#` are treated as comments and ignored."""
    result = _parse_properties("# this is a comment\naudit.logger = on\n")
    assert "audit.logger" in result
    assert len(result) == 1


def test_parse_properties_bang_comment_ignored() -> None:
    """Lines starting with `!` are treated as comments and ignored."""
    result = _parse_properties("! another comment form\naudit.database = off\n")
    assert "audit.database" in result
    assert len(result) == 1


def test_parse_properties_duplicate_key_last_wins() -> None:
    """When a key appears twice the last value wins (Java Properties semantics)."""
    text = "audit.logger = off\naudit.logger = on\n"
    result = _parse_properties(text)
    assert result["audit.logger"] == "on"


def test_parse_properties_empty_value() -> None:
    """A key with an empty value after `=` is stored as an empty string."""
    result = _parse_properties("audit.metadata =\n")
    assert result["audit.metadata"] == ""


def test_parse_properties_value_with_equals() -> None:
    """A value that contains `=` is stored correctly (first `=` is the separator, the rest is the value)."""
    # e.g. encryption.password = BASE64=ENCODED=VALUE
    result = _parse_properties("encryption.password = BASE64=ENCODED=VALUE\n")
    assert result["encryption.password"] == "BASE64=ENCODED=VALUE"


def test_parse_properties_value_with_equals_reports_is_set(tmp_path: Path) -> None:
    """A confidential key whose value contains `=` reports is_set=True and never surfaces the value."""
    conf = tmp_path / "dhis.conf"
    conf.write_text("encryption.password = BASE64=ENCODED=SUPER-SECRET\nconnection.url = jdbc:db\n", encoding="utf-8")
    posture = parse_dhis_conf(conf)
    by_key = {s.key: s for s in posture.secrets}
    assert by_key["encryption.password"].is_set is True
    # The value must not appear in the model dump.
    assert "BASE64" not in posture.model_dump_json()
    assert "SUPER-SECRET" not in posture.model_dump_json()


def test_parse_properties_blank_lines_and_whitespace_ignored() -> None:
    """Blank lines and leading/trailing whitespace on key names are handled."""
    text = "\n   audit.logger = on   \n\n   audit.database = off\n"
    result = _parse_properties(text)
    assert result == {"audit.logger": "on", "audit.database": "off"}


# ---------------------------------------------------------------------------
# _split_property
# ---------------------------------------------------------------------------


def test_split_property_equals() -> None:
    """An `=`-separated line splits into (key, '=', value)."""
    key, sep, value = _split_property("audit.logger = on")
    assert key == "audit.logger"
    assert sep == "="
    assert value == "on"


def test_split_property_colon() -> None:
    """A `:`-separated line splits into (key, ':', value)."""
    key, sep, value = _split_property("audit.logger: on")
    assert key == "audit.logger"
    assert sep == ":"
    assert value == "on"


def test_split_property_first_separator_wins() -> None:
    """When both `:` and `=` appear the leftmost one is the separator; the rest is value."""
    key, sep, value = _split_property("key=val:extra")
    assert key == "key"
    assert sep == "="
    assert value == "val:extra"


def test_split_property_no_separator() -> None:
    """A line with no separator returns the line as key, None separator, empty value."""
    key, sep, value = _split_property("no-separator-here")
    assert key == "no-separator-here"
    assert sep is None
    assert value == ""


# ---------------------------------------------------------------------------
# _parse_matrix
# ---------------------------------------------------------------------------


def test_parse_matrix_standard_types() -> None:
    """A standard semicolon-separated matrix string is parsed into the correct tuple."""
    result = _parse_matrix("CREATE;UPDATE;DELETE;SECURITY")
    assert set(result) == {"CREATE", "UPDATE", "DELETE", "SECURITY"}


def test_parse_matrix_lowercase_types() -> None:
    """Lowercase tokens are uppercased and recognised correctly."""
    result = _parse_matrix("create;update")
    assert set(result) == {"CREATE", "UPDATE"}


def test_parse_matrix_disabled_sentinel() -> None:
    """The DISABLED token produces an empty type set (documented DHIS2 behavior)."""
    result = _parse_matrix("DISABLED")
    assert result == ()


def test_parse_matrix_empty_string() -> None:
    """An empty string produces an empty tuple (caller applies the DHIS2 default)."""
    result = _parse_matrix("")
    assert result == ()


def test_parse_matrix_blank_tokens_skipped() -> None:
    """Blank tokens (e.g. trailing semicolons) are skipped."""
    result = _parse_matrix("CREATE;;UPDATE;")
    assert set(result) == {"CREATE", "UPDATE"}


def test_parse_matrix_deduplicates() -> None:
    """Duplicate tokens in the matrix string are deduplicated."""
    result = _parse_matrix("CREATE;CREATE;UPDATE")
    assert result.count("CREATE") == 1


def test_parse_matrix_explicit_narrow() -> None:
    """A matrix with only READ is narrow relative to the forensic default."""
    result = _parse_matrix("READ")
    assert result == ("READ",)
    # READ is a valid type but omits the four forensic types.
    forensic = {"CREATE", "UPDATE", "DELETE", "SECURITY"}
    assert forensic.isdisjoint(set(result))
