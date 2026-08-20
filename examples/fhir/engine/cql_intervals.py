"""Say "during the reporting period" in CQL: interval literals, membership, and timing operators.

Almost every quality measure is bounded by time - a reporting period, an age band, a window after an
event. CQL gives that its own first-class type, the **Interval**, so none of it is written as pairs
of comparisons.

An interval has a low bound, a high bound, and a square bracket or a round one on each end: square
means the bound is included, round means it is not. `Interval[1, 10]` holds 10; `Interval[1, 10)`
does not. That distinction is the reason a period ending "31 December" and one ending "1 January"
count the same days.

Once you have intervals, the timing vocabulary reads as English: `during`, `before`, `after`,
`overlaps`, `starts`, `ends`. A measure's `"Measurement Period"` parameter is an interval, and
`ToDate(I.occurrenceDateTime) during "Measurement Period"` is the whole of "this dose counts for
this period". The `ToDate` is doing real work: a FHIR resource carries its dates as strings, and
`ToDate` is what turns one into a value the timing operators can place on a line.

Usage:
    uv run python examples/fhir/engine/cql_intervals.py

Needs no DHIS2, no server, and no project: every expression is self-contained.
"""

from __future__ import annotations

from _bundle import clinic_bundle
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r4 import BundleDataSource
from pydantic import BaseModel

#: Interval expressions and what each one is for, evaluated with no library and no data at all.
INTERVAL_EXPRESSIONS: tuple[tuple[str, str], ...] = (
    ("Interval[1, 10]", "a closed interval - both bounds are inside it"),
    ("5 in Interval[1, 10]", "membership: is a point inside?"),
    ("10 in Interval[1, 10)", "the round bracket excludes the high bound"),
    ("width of Interval[1, 10]", "how wide the interval is"),
    ("start of Interval[@2024-01-01, @2024-12-31]", "the low bound, as a value"),
    ("end of Interval[@2024-01-01, @2024-12-31]", "the high bound, as a value"),
    ("@2024-06-11 during Interval[@2024-01-01, @2024-12-31]", "a date inside a reporting period"),
    ("@2025-01-04 during Interval[@2024-01-01, @2024-12-31]", "a date outside it"),
    ("Interval[@2024-01-01, @2024-03-31] during Interval[@2024-01-01, @2024-12-31]", "a quarter inside a year"),
    ("Interval[1, 3] before Interval[5, 9]", "one interval wholly before another"),
    ("Interval[1, 5] overlaps Interval[4, 9]", "two intervals sharing at least one point"),
    ("Interval[1, 5] intersect Interval[4, 9]", "the part they share, as an interval"),
    ("duration in days between @2024-01-01 and @2024-01-15", "the distance between two dates"),
)

DOSES_IN_PERIOD_LIBRARY = """
library DosesInPeriod version '1.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1'

parameter "Measurement Period" Interval<Date>
    default Interval[@2024-01-01, @2024-06-30]

define "Doses In Period":
    [Immunization] I
        where ToDate(I.occurrenceDateTime) during "Measurement Period"

define "Dose Count In Period":
    Count("Doses In Period")
"""


class IntervalAnswer(BaseModel):
    """One interval expression, what it is for, and what the engine answered."""

    expression: str
    purpose: str
    answer: str

    def rendered(self) -> str:
        """The line as it prints: expression, answer, then the reason in the margin."""
        return f"  {self.expression:76} {self.answer:34} {self.purpose}"


def main() -> None:
    """Evaluate the interval vocabulary on its own, then use an interval to bound a real retrieve."""
    plain = CQLEvaluator()

    print("intervals on their own - no library, no data source, no data:")
    for expression, purpose in INTERVAL_EXPRESSIONS:
        answer = IntervalAnswer(
            expression=expression,
            purpose=purpose,
            answer=str(plain.evaluate_expression(expression)),
        )
        print(answer.rendered())

    print()
    evaluator = CQLEvaluator(data_source=BundleDataSource(clinic_bundle()))
    evaluator.compile(DOSES_IN_PERIOD_LIBRARY)

    period = evaluator.get_parameters()["Measurement Period"]
    in_period = evaluator.evaluate_definition("Doses In Period")
    print(f'the library\'s default "Measurement Period": {period}')
    print(f"  doses whose occurrenceDateTime falls during it: {[dose['id'] for dose in in_period]}")
    print(f"  Count -> {evaluator.evaluate_definition('Dose Count In Period')} of 4 recorded doses")

    # The caller can hand a different period in without touching the library - which is how one
    # measure definition is run for January, for a quarter, and for a year.
    second_half = plain.evaluate_expression("Interval[@2024-07-01, @2024-12-31]")
    later = evaluator.evaluate_definition("Doses In Period", parameters={"Measurement Period": second_half})
    print()
    print(f"the same definition with the caller's own period {second_half}:")
    print(f"  -> {[dose['id'] for dose in later]}")
    print()
    print("The library states the question once. The period is an argument, so the answer moves with it.")


if __name__ == "__main__":
    main()
