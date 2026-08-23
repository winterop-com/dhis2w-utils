"""The library half of the identity dial: reading one person's nominated values, and checking the nomination.

The register is the first consumer and not the only one intended: a summary document reads a person
the same way, so the reading lives here rather than in the server. `docs/fhir/design/ips.md`
section 4.
"""

from __future__ import annotations

from dhis2w_fhir.ips import (
    ADMINISTRATIVE_GENDER_CODES,
    DATA_ABSENT_ERROR,
    DATA_ABSENT_UNKNOWN,
    IdentityNominations,
    nominated_value_type_issues,
    served_identity,
)
from dhis2w_fhir.r4 import DATA_ABSENT_REASON_EXTENSION_URL

_NAME_ATTRIBUTE = "w75KJ2mc4zz"
_BIRTH_DATE_ATTRIBUTE = "iESIqZ0R0R0"
_SEX_ATTRIBUTE = "cejWyOfXge6"

_NOMINATIONS = IdentityNominations(
    name=_NAME_ATTRIBUTE,
    birth_date=_BIRTH_DATE_ATTRIBUTE,
    sex=_SEX_ATTRIBUTE,
    administrative_gender={"Male": "male", "Female": "female"},
)


def _absence_code(nominations: IdentityNominations, values: dict[str, str]) -> str | None:
    """The data-absent-reason one reading states on `_birthDate`, or None where it states none."""
    element = served_identity(values, nominations).birth_date_element
    if element is None or element.extension is None:
        return None
    return next(
        extension.valueCode for extension in element.extension if extension.url == DATA_ABSENT_REASON_EXTENSION_URL
    )


def test_the_four_administrative_gender_codes_are_the_whole_binding() -> None:
    """The binding is required, so the set a nomination may map onto is closed and stated once."""
    assert ADMINISTRATIVE_GENDER_CODES == ("male", "female", "other", "unknown")


def test_a_nominated_reading_fills_the_three_elements() -> None:
    """A name is a nomination or it is nothing, and this is what a nomination reads."""
    identity = served_identity(
        {_NAME_ATTRIBUTE: "Anna Nkemelu", _BIRTH_DATE_ATTRIBUTE: "2001-02-03", _SEX_ATTRIBUTE: "Female"},
        _NOMINATIONS,
    )

    assert identity.name is not None
    assert [name.text for name in identity.name] == ["Anna Nkemelu"]
    assert identity.birth_date == "2001-02-03"
    assert identity.gender == "female"
    assert identity.birth_date_element is None


def test_a_name_of_whitespace_alone_is_nothing_stated() -> None:
    """DHIS2 accepts a value of three spaces, and a name of three spaces is not one anybody can read."""
    assert served_identity({_NAME_ATTRIBUTE: "   "}, _NOMINATIONS).name is None


def test_a_name_keeps_its_own_spelling_and_loses_only_its_edges() -> None:
    """The value is the instance's, so nothing is capitalised, reordered, or split into halves."""
    identity = served_identity({_NAME_ATTRIBUTE: "  de la Cruz, María  "}, _NOMINATIONS)

    assert identity.name is not None
    assert identity.name[0].text == "de la Cruz, María"
    assert identity.name[0].family is None
    assert identity.name[0].given is None


def test_a_missing_birth_date_states_unknown_and_an_unreadable_one_states_error() -> None:
    """An instance-wide nomination is a statement about the attribute, not a promise about every row."""
    assert _absence_code(_NOMINATIONS, {}) == DATA_ABSENT_UNKNOWN
    assert _absence_code(_NOMINATIONS, {_BIRTH_DATE_ATTRIBUTE: "circa 2001"}) == DATA_ABSENT_ERROR


def test_a_project_nominating_no_birth_date_states_no_absence() -> None:
    """An element nobody asked for is not an element with something missing."""
    assert _absence_code(IdentityNominations(name=_NAME_ATTRIBUTE), {}) is None


def test_a_reading_over_no_nominations_states_nothing_at_all() -> None:
    """The default table is what every project written before it said, and it fills no element."""
    identity = served_identity({_NAME_ATTRIBUTE: "Anna Nkemelu"}, IdentityNominations())

    assert identity.name is None
    assert identity.gender is None
    assert identity.birth_date is None
    assert identity.birth_date_element is None


def test_a_value_type_the_element_cannot_take_is_an_issue_naming_the_key() -> None:
    """The refusal names the key, the attribute, and the type it found - not just that something is wrong."""
    issues = nominated_value_type_issues(
        _NOMINATIONS,
        {_NAME_ATTRIBUTE: "TEXT", _BIRTH_DATE_ATTRIBUTE: "INTEGER_POSITIVE", _SEX_ATTRIBUTE: "TEXT"},
    )

    assert [issue.key for issue in issues] == ["birth_date"]
    message = issues[0].message()
    assert _BIRTH_DATE_ATTRIBUTE in message
    assert "INTEGER_POSITIVE" in message
    assert "DATE" in message


def test_an_attribute_the_guide_publishes_nothing_about_raises_no_issue() -> None:
    """The guide's silence means the attribute is outside this project's selection, not that it is wrong."""
    assert nominated_value_type_issues(_NOMINATIONS, {}) == []


def test_a_long_text_attribute_may_carry_a_name() -> None:
    """DHIS2 spells a free-text attribute three ways, and a person's name arrives in any of them."""
    assert nominated_value_type_issues(IdentityNominations(name=_NAME_ATTRIBUTE), {_NAME_ATTRIBUTE: "LONG_TEXT"}) == []
