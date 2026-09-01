"""Grouping one `/api/dataValueSets` envelope into the forms it reports - the key both readers key on.

DHIS2 answers a data value set as a flat list of values, and a form is a group of them: one data
set, reported for one period, at one organisation unit, under one attribute option combo. That
triple is the reporting key, and every consumer of the endpoint has to reconstruct it - the examples
target does it to publish a corpus, and the facade's data set read-back does it to serve a document.

THE FALL-BACK IS THE SUBTLE PART, AND IT IS WRITTEN ONCE HERE. A data value may name its own period,
organisation unit, and attribute option combo, and DHIS2 reads the envelope's as the default for the
ones it does not - so a value's own key comes first and the envelope's stands behind it, exactly as
`dhis2w_fhir.overwrite.aggregate_cells` reads the same envelope for the same reason. A reader that
took the value's key alone would file every value of a single-period export under the empty string
and call them one form.

The period a caller asked for is the third and last fall-back, and it applies to the period alone: a
read that named one period and got back an envelope stating none is still a read of that period. It
is stated rather than inferred, because a read naming several periods has no single period to fall
back to and must not invent one.

The groups come back in the order the envelope first names each of them, so a caller that wants an
order says which one it wants: the examples target picks the richest group, the read-back sorts on
the reporting key itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.oas import DataValueSet

__all__ = [
    "ReportedForm",
    "ReportedValue",
    "group_data_values",
]


class ReportedValue(BaseModel):
    """One value a form reports, keyed the way DHIS2 keys a cell: data element crossed with combo."""

    model_config = ConfigDict(frozen=True)

    data_element_uid: str
    category_option_combo_uid: str | None = None
    """None where the data element rides the default category combo, which is what DHIS2 files it under."""

    value: str


class ReportedForm(BaseModel):
    """One reporting key of a data value set - the triple DHIS2 files a form under - and its values."""

    model_config = ConfigDict(frozen=True)

    organisation_unit_uid: str
    """Empty where neither the value nor the envelope named one, which no DHIS2 export produces."""

    period_iso: str
    """Empty where neither the value, the envelope, nor the caller named one."""

    attribute_option_combo_uid: str | None = None
    """None where the data set rides the default category combo, which is what DHIS2 files it under."""

    values: tuple[ReportedValue, ...] = ()

    @property
    def reporting_key(self) -> tuple[str, str, str]:
        """The triple this form is filed under, as a total order two reads of one period sort the same by."""
        return (self.organisation_unit_uid, self.period_iso, self.attribute_option_combo_uid or "")


def group_data_values(
    data_value_set: DataValueSet, *, default_period_iso: str | None = None
) -> tuple[ReportedForm, ...]:
    """Group one data value set into the forms it reports, first-named first.

    `default_period_iso` is the period the caller asked for, which stands behind the value's own and
    the envelope's - see the module docstring for why it is the caller's to state.
    """
    grouped: dict[tuple[str, str, str | None], list[ReportedValue]] = {}
    for value in data_value_set.dataValues or []:
        if not value.dataElement or value.value is None:
            continue
        key = (
            value.orgUnit or data_value_set.orgUnit or "",
            value.period or data_value_set.period or default_period_iso or "",
            value.attributeOptionCombo or data_value_set.attributeOptionCombo,
        )
        grouped.setdefault(key, []).append(
            ReportedValue(
                data_element_uid=value.dataElement,
                category_option_combo_uid=value.categoryOptionCombo,
                value=value.value,
            )
        )
    return tuple(
        ReportedForm(
            organisation_unit_uid=organisation_unit_uid,
            period_iso=period_iso,
            attribute_option_combo_uid=attribute_option_combo_uid,
            values=tuple(values),
        )
        for (organisation_unit_uid, period_iso, attribute_option_combo_uid), values in grouped.items()
    )
