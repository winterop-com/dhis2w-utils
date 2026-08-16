"""Check a submission against the capture contract in your own process, before any of it is sent.

`validate_response` is the whole of what a facade decides a POST on, and it is an ordinary
function over bytes: no server, no socket, no DHIS2. A capture client can therefore run the exact
check the facade will run, on the machine holding the form, and refuse to send a submission it
already knows will come back refused - which is what keeps a tablet in a clinic from queuing work
that can only fail later.

Three things it needs, and all three come off the project on disk:

- the **contract names** (`CaptureNaming`) - which extension URLs this project writes its reporting
  period, its DHIS2 form kind, and its organisation unit under, derived from `fhir.toml`;
- the **published guide** (`ResourceStore`) - the compiled forms and terminology a submission is
  checked against, which is what `d2w fhir generate` and the SUSHI compile produced;
- an **index cache** (`CaptureIndexCache`) - one form flattened into lookups, built on first use.

The checks run in phases and the first phase to find an error is the last one to run: there is no
point telling a reporter its values are wrong when the server could not tell which data set the
submission is for. Inside one phase every problem is collected, so the refusal below names two
things at once rather than one per round trip.

Usage:
    uv run python examples/fhir/client/validate_before_sending.py
"""

from __future__ import annotations

from typing import Literal

from _fixture import aggregate_form_id, capture_store, example_project
from dhis2w_fhir import load_project
from dhis2w_fhir.r4 import Extension, Period, QuestionnaireResponse, Reference
from dhis2w_fhir_serve.capture import (
    PERIOD_ISO_SUB_EXTENSION,
    PERIOD_RANGE_SUB_EXTENSION,
    PERIOD_TYPE_SUB_EXTENSION,
    CaptureIndex,
    CaptureIndexCache,
    CaptureNaming,
    CaptureRejection,
    ValidatedCapture,
    validate_response,
)
from dhis2w_fhir_serve.store import ResourceStore, SearchQuery

ReportStatus = Literal["completed", "in-progress"]
"""The two states this example submits a data set report in: finished, and still being filled in."""


def monthly_report(
    canonical: str,
    naming: CaptureNaming,
    organisation_unit: str,
    *,
    status: ReportStatus,
    period: Extension | None,
) -> bytes:
    """One data set report as the bytes a capture server would receive it as."""
    form_type = Extension(url=naming.form_type_url, valueCode="aggregate")
    report = QuestionnaireResponse(
        questionnaire=canonical,
        status=status,
        # An aggregate report reports *for a place*, so the organisation unit is the subject.
        subject=Reference(reference=organisation_unit),
        extension=[form_type] if period is None else [form_type, period],
    )
    return report.model_dump_json(exclude_none=True).encode()


def reporting_period(naming: CaptureNaming) -> Extension:
    """January 2026 as the three facts DHIS2 needs: the period, its frequency, and the dates it covers."""
    return Extension(
        url=naming.period_url,
        extension=[
            Extension(url=PERIOD_ISO_SUB_EXTENSION, valueString="202601"),
            Extension(url=PERIOD_TYPE_SUB_EXTENSION, valueCode="Monthly"),
            Extension(url=PERIOD_RANGE_SUB_EXTENSION, valuePeriod=Period(start="2026-01-01", end="2026-01-31")),
        ],
    )


def reporting_unit(index: CaptureIndex, store: ResourceStore) -> str:
    """An organisation unit the form may be reported for, as the `Location/<uid>` a submission names it by."""
    # A form publishes the organisation units it is assigned to as a List. Reporting for a unit
    # outside that assignment is what DHIS2 refuses at import with E1029. A form that publishes no
    # assignment is open to every unit the guide published, so any one of them will do.
    if index.assignment is not None:
        return sorted(index.assignment.references)[0]
    return f"Location/{store.search('Location', SearchQuery())[0].resource_id}"


def report_on(captured: ValidatedCapture) -> None:
    """Print what a submission that cleared every phase was understood as."""
    print(f"  accepted as form kind `{captured.form_kind}`, answering {captured.canonical}")
    for warning in captured.warnings:
        print(f"    noted [{warning.code}] {warning.diagnostics}")
    if not captured.warnings:
        print("    nothing to note")


def main() -> None:
    """Check one report that clears the contract and one that does not, without sending either."""
    project = load_project(example_project())
    naming = CaptureNaming.from_project(project)
    store = capture_store()
    indexes = CaptureIndexCache()

    form = store.by_type_and_id("Questionnaire", aggregate_form_id())
    if form is None or form.canonical_url is None:
        print(f"the guide publishes no form `{aggregate_form_id()}` - run `d2w fhir generate` and compile it")
        return
    index = indexes.resolve(form.canonical_url, naming, store)
    organisation_unit = reporting_unit(index, store)
    print(f"checking against {form.canonical_url}, reported at {organisation_unit}")

    # A finished monthly report. Nothing is answered, which is deliberate: an unanswered question is
    # DHIS2's to enforce at import, so the envelope alone is a submission the contract admits.
    print("\na finished report for January 2026:")
    report_on(
        validate_response(
            monthly_report(
                form.canonical_url,
                naming,
                organisation_unit,
                status="completed",
                period=reporting_period(naming),
            ),
            indexes,
            naming,
            store,
        )
    )

    # The same report still being filled in, and reporting for no period. Both faults sit in the
    # same phase, so one check names both - a client fixes them in one pass rather than in two.
    print("\nthe same report, still being filled in, naming no period:")
    try:
        validate_response(
            monthly_report(form.canonical_url, naming, organisation_unit, status="in-progress", period=None),
            indexes,
            naming,
            store,
        )
    except CaptureRejection as rejection:
        print(f"  refused, and a server would answer HTTP {rejection.http_status}:")
        for issue in rejection.issues:
            print(f"    [{issue.code}] {issue.expression}")
            print(f"      {issue.diagnostics}")


if __name__ == "__main__":
    main()
