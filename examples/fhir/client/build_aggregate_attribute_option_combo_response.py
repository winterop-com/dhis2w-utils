"""Report a data set whose own category combination is not the default: the second key DHIS2 files under.

A DHIS2 data value is filed under four keys, not three. Everyone knows the first three - data
element, period, organisation unit. The fourth is the **attribute option combo**, and it comes from
the *data set's own* category combination rather than from any data element's.

That dimension keys the whole submission. A data set on a "Project" category combination is
reported once per project: the same data elements, the same period, the same facility, reported
separately for "Improve access to clean water" and for "Provide access to primary health care", and
DHIS2 stores both without either overwriting the other. Most data sets are on the default
combination, have exactly one attribute option combo, and never think about it.

The form says which case it is. A data set on a non-default combination publishes the vocabulary its
submissions are keyed by - a `D2AttributeOptionCombos` extension on the `Questionnaire` naming a
ValueSet - and a response answering that form has to carry a `D2AttributeOptionCombo` picked out of
it. A data set on the default combination publishes neither, because absence means the default.

The answer is a **Coding**: FHIR's "a code, and the vocabulary it is a code from". The vocabulary is
this guide's own CodeSystem for that category combination, and under the default `id` naming the
codes are the DHIS2 category option combo UIDs.

Usage:
    uv run python examples/fhir/client/build_aggregate_attribute_option_combo_response.py

Requires a DHIS2 profile (`d2w profile list`).
"""

from __future__ import annotations

from _fixture import attribute_option_combo_form_id, conversion_context, form_canonical
from _runner import run_example
from dhis2w_fhir import translate_response
from dhis2w_fhir.r4 import (
    Coding,
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Gbenikoro MCHP, a facility the seeded instance assigns EPI Stock to.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

REPORTING_PERIOD = "202601"
REPORTING_PERIOD_TYPE = "Monthly"

#: Which project this submission reports for - one of the four the "Project" category combination
#: offers. Report the same period and facility again under another one and DHIS2 keeps both.
ATTRIBUTE_OPTION_COMBO_CODE = "BqblOcSwGey"

#: Stock counted against three of the data set's undisaggregated data elements.
COUNTED_STOCK = {
    "p1MDHOT6ENy": 120,
    "lVknokmR4Ip": 45,
    "FTINmL2lehN": 8,
}


async def main() -> None:
    """Report a data set on a non-default attribute category combination, naming which cut it reports."""
    context = conversion_context()
    canonical = form_canonical(attribute_option_combo_form_id())
    form = context.forms[canonical]

    if form.attribute_option_combo_system is None:
        print(f"{canonical.rsplit('/', 1)[-1]} is on the default category combination and needs no key")
        return

    # What the form published about its own keying, and the codes a response may pick from.
    print(f"form {canonical.rsplit('/', 1)[-1]} is keyed by {form.attribute_option_combo_value_set}")
    table = context.option_tables.get(form.attribute_option_combo_system)
    for entry in table.entries if table else ():
        chosen = " <- this submission" if entry.concept_code == ATTRIBUTE_OPTION_COMBO_CODE else ""
        print(f"  {entry.concept_code}  DHIS2 code {entry.option_code}{chosen}")

    response = QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="aggregate"),
            Extension(
                url=context.naming.period_url,
                extension=[
                    Extension(url="iso", valueString=REPORTING_PERIOD),
                    Extension(url="type", valueCode=REPORTING_PERIOD_TYPE),
                ],
            ),
            # The fourth key. `system` says which vocabulary the code is from - the form named it,
            # so a client never invents it - and `code` is the one option this submission reports.
            Extension(
                url=context.naming.attribute_option_combo_url,
                valueCoding=Coding(
                    system=form.attribute_option_combo_system,
                    code=ATTRIBUTE_OPTION_COMBO_CODE,
                ),
            ),
        ],
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        item=[
            QuestionnaireResponseItem(
                linkId=link_id,
                answer=[QuestionnaireResponseAnswer(valueDecimal=counted)],
            )
            for link_id, counted in COUNTED_STOCK.items()
        ],
    )

    print()
    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    # The proof: the key rides on the envelope, so it lands once on the data value set rather than
    # on each data value - which is exactly what "keys the whole submission" means.
    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.data_value_set is not None:
        print(
            f"\nconverts to a {result.target_kind}: data set {result.data_value_set.dataSet}, "
            f"period {result.data_value_set.period}, organisation unit {result.data_value_set.orgUnit}, "
            f"attribute option combo {result.data_value_set.attributeOptionCombo}, "
            f"{len(result.data_value_set.dataValues or [])} data value(s)"
        )


if __name__ == "__main__":
    run_example(main)
