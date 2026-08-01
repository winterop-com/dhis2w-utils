"""Unit tests for dhis2w_fhir.names slug and escaping helpers."""

from dhis2w_fhir.names import code_or_uid, fsh_code, is_valid_fhir_code, kebab, pascal, quote


def test_pascal_collapses_punctuation() -> None:
    """Free text with punctuation collapses to PascalCase."""
    assert pascal("Birth type") == "BirthType"
    assert pascal("ANC 1st visit (fixed)") == "ANC1stVisitFixed"


def test_pascal_never_starts_with_digit() -> None:
    """A digit-leading result gets the fallback prefixed."""
    assert pascal("1st visit") == "Generated1stVisit"


def test_pascal_empty_uses_fallback() -> None:
    """Empty or symbol-only input falls back."""
    assert pascal("") == "Generated"
    assert pascal("!!!", fallback="Fallback") == "Fallback"


def test_kebab_lowercases_and_joins() -> None:
    """Free text becomes a kebab-case slug."""
    assert kebab("Birth type") == "birth-type"
    assert kebab("ANC 1st visit (fixed)") == "anc-1st-visit-fixed"
    assert kebab("") == "generated"


def test_quote_escapes_and_flattens() -> None:
    """Backslashes and quotes are escaped; newlines and runs of whitespace flatten to one space."""
    assert quote('say "hi"') == '"say \\"hi\\""'
    assert quote("back\\slash") == '"back\\\\slash"'
    assert quote("line one\nline  two") == '"line one line two"'


def test_fsh_code_quotes_spaces() -> None:
    """Codes with spaces use the quoted form."""
    assert fsh_code("ABC123") == "#ABC123"
    assert fsh_code("ANC 01") == '#"ANC 01"'


def test_fsh_code_escapes_like_quote() -> None:
    """The quoted form escapes backslashes and double quotes exactly as `quote` does."""
    assert fsh_code('say "hi" now') == '#"say \\"hi\\" now"'
    assert fsh_code("back\\slash here") == '#"back\\\\slash here"'
    assert fsh_code('both \\ and " here') == '#"both \\\\ and \\" here"'
    assert fsh_code('say "hi" now')[2:-1] == quote('say "hi" now')[1:-1]


def test_code_or_uid_falls_back() -> None:
    """The code slot carries the DHIS2 code when usable and repeats the UID otherwise."""
    assert code_or_uid("SL", "ImspTQPwCqd") == "SL"
    assert code_or_uid("two words", "ImspTQPwCqd") == "two words"
    assert code_or_uid(None, "ImspTQPwCqd") == "ImspTQPwCqd"
    assert code_or_uid("", "ImspTQPwCqd") == "ImspTQPwCqd"
    assert code_or_uid(" padded ", "ImspTQPwCqd") == "ImspTQPwCqd"


def test_is_valid_fhir_code() -> None:
    """FHIR code datatype: non-empty, no leading/trailing/double whitespace."""
    assert is_valid_fhir_code("ANC-01")
    assert is_valid_fhir_code("two words")
    assert not is_valid_fhir_code(None)
    assert not is_valid_fhir_code("")
    assert not is_valid_fhir_code(" leading")
    assert not is_valid_fhir_code("trailing ")
    assert not is_valid_fhir_code("double  space")
    assert not is_valid_fhir_code("tab\tinside")
