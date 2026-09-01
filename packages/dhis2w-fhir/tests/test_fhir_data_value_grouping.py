"""Grouping one `/api/dataValueSets` envelope into the forms it reports - the rule both readers share.

The examples target builds a published corpus out of these groups and the FHIR facade serves a
document per group, so the fall-back rule is written once and pinned here: a value's own reporting
key first, the envelope's behind it, and the period a caller asked for behind that.

The envelope fall-back is the case worth pinning by name. A single-period, single-unit export states
the keys once on the envelope and leaves every value bare, and a reader that took the value's own key
alone would file all of them under the empty string and call them one form with no organisation unit
to name.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.generated.v42.oas import DataValueSet
from dhis2w_fhir import group_data_values


def _value(**stated: Any) -> dict[str, Any]:
    """One data value as `/api/dataValueSets` exports it, carrying only the keys the case is about."""
    return stated


def _envelope(*values: dict[str, Any], **keys: Any) -> DataValueSet:
    """One export envelope, validated the way the two readers validate it."""
    return DataValueSet.model_validate({"dataValues": list(values), **keys})


def test_a_value_states_its_own_reporting_key() -> None:
    """The three keys off the value itself, which is what a multi-unit export carries on every row."""
    envelope = _envelope(
        _value(
            dataElement="De1aaaaaaaa",
            categoryOptionCombo="Coc1aaaaaaa",
            orgUnit="Ou1aaaaaaaa",
            period="202606",
            attributeOptionCombo="Aoc1aaaaaaa",
            value="11",
        )
    )

    [form] = group_data_values(envelope)

    assert form.reporting_key == ("Ou1aaaaaaaa", "202606", "Aoc1aaaaaaa")
    assert form.values[0].data_element_uid == "De1aaaaaaaa"
    assert form.values[0].category_option_combo_uid == "Coc1aaaaaaa"
    assert form.values[0].value == "11"


def test_a_value_naming_no_key_takes_the_envelopes() -> None:
    """DHIS2 reads the envelope's keys as the default for a value that names none, and so does this."""
    envelope = _envelope(
        _value(dataElement="De1aaaaaaaa", categoryOptionCombo="Coc1aaaaaaa", value="11"),
        _value(dataElement="De2aaaaaaaa", categoryOptionCombo="Coc1aaaaaaa", value="22"),
        orgUnit="Ou1aaaaaaaa",
        period="202606",
        attributeOptionCombo="Aoc1aaaaaaa",
    )

    [form] = group_data_values(envelope)

    assert form.reporting_key == ("Ou1aaaaaaaa", "202606", "Aoc1aaaaaaa")
    assert [value.value for value in form.values] == ["11", "22"]


def test_a_value_that_states_a_key_wins_over_the_envelope() -> None:
    """The envelope is a default and not an assertion, so a value reported elsewhere stays elsewhere."""
    envelope = _envelope(
        _value(dataElement="De1aaaaaaaa", value="11"),
        _value(dataElement="De2aaaaaaaa", orgUnit="Ou2aaaaaaaa", value="22"),
        orgUnit="Ou1aaaaaaaa",
        period="202606",
    )

    forms = {form.organisation_unit_uid: form for form in group_data_values(envelope)}

    assert set(forms) == {"Ou1aaaaaaaa", "Ou2aaaaaaaa"}
    assert forms["Ou2aaaaaaaa"].period_iso == "202606"


def test_the_period_a_caller_asked_for_stands_behind_both() -> None:
    """A read that named one period and got an envelope stating none is still a read of that period."""
    envelope = _envelope(_value(dataElement="De1aaaaaaaa", orgUnit="Ou1aaaaaaaa", value="11"))

    [stated] = group_data_values(envelope, default_period_iso="202606")
    [unstated] = group_data_values(envelope)

    assert stated.period_iso == "202606"
    assert unstated.period_iso == ""


def test_the_default_category_combo_is_an_absence_rather_than_a_word() -> None:
    """DHIS2 files a value under the default combo without naming one, and the group says so the same way."""
    envelope = _envelope(_value(dataElement="De1aaaaaaaa", orgUnit="Ou1aaaaaaaa", period="202606", value="11"))

    [form] = group_data_values(envelope)

    assert form.attribute_option_combo_uid is None
    assert form.values[0].category_option_combo_uid is None
    assert form.reporting_key == ("Ou1aaaaaaaa", "202606", "")


def test_two_attribute_option_combos_are_two_forms() -> None:
    """The combo is the third key, so one unit and one period can report several forms at once."""
    envelope = _envelope(
        _value(dataElement="De1aaaaaaaa", attributeOptionCombo="Aoc1aaaaaaa", value="11"),
        _value(dataElement="De1aaaaaaaa", attributeOptionCombo="Aoc2aaaaaaa", value="22"),
        orgUnit="Ou1aaaaaaaa",
        period="202606",
    )

    forms = group_data_values(envelope)

    assert [form.attribute_option_combo_uid for form in forms] == ["Aoc1aaaaaaa", "Aoc2aaaaaaa"]
    assert all(len(form.values) == 1 for form in forms)


def test_the_groups_come_back_in_the_order_the_envelope_first_names_them() -> None:
    """No order is imposed here: a caller that wants one says which, and both callers do."""
    envelope = _envelope(
        _value(dataElement="De1aaaaaaaa", orgUnit="Ou2aaaaaaaa", period="202606", value="11"),
        _value(dataElement="De1aaaaaaaa", orgUnit="Ou1aaaaaaaa", period="202606", value="22"),
        _value(dataElement="De2aaaaaaaa", orgUnit="Ou2aaaaaaaa", period="202606", value="33"),
    )

    forms = group_data_values(envelope)

    assert [form.organisation_unit_uid for form in forms] == ["Ou2aaaaaaaa", "Ou1aaaaaaaa"]
    assert len(forms[0].values) == 2


def test_a_value_the_instance_states_nothing_for_is_not_a_reported_value() -> None:
    """A row with no data element or no value names no cell, so it joins no form rather than an empty one."""
    envelope = _envelope(
        _value(dataElement="De1aaaaaaaa", orgUnit="Ou1aaaaaaaa", period="202606", value="11"),
        _value(orgUnit="Ou1aaaaaaaa", period="202606", value="22"),
        _value(dataElement="De2aaaaaaaa", orgUnit="Ou1aaaaaaaa", period="202606"),
    )

    [form] = group_data_values(envelope)

    assert [value.data_element_uid for value in form.values] == ["De1aaaaaaaa"]


def test_an_envelope_carrying_no_values_reports_no_forms() -> None:
    """An instance holding nothing for the selection is an empty answer, not a form with nothing in it."""
    assert group_data_values(_envelope(orgUnit="Ou1aaaaaaaa", period="202606")) == ()
