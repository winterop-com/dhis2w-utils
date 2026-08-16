"""The aggregate values a drain sends that an earlier submission already sent, and the index that finds them.

DHIS2 cannot answer this question, so the spool does. `/api/dataValueSets` applies its own
`CREATE_AND_UPDATE` to an envelope that names no strategy, so a second send of one cell replaces the
first in place; and the import summary counts `updated: 1` for a genuinely first write and for a
replacement alike (BUGS.md 85), so nothing DHIS2 answers separates the two. What separates them here
is the record every drained receipt leaves: a forwarded receipt's `<id>.report.json` names the cells
its payload put in the instance, and the next drain reads those records back before it sends anything.

The cell is the full DHIS2 identity of a data value - data element, category option combo, period,
organisation unit, and attribute option combo - because that tuple is what DHIS2 keys a value on, and
anything shorter would call two different cells the same one.

THE SIDECAR IS THE RECORD, NOT THE RECEIPT. A forwarded receipt holds the FHIR submission, which
means the cells it landed on are only knowable by translating it again - against today's guide, which
may no longer be the guide it was sent under. The sidecar instead states what was actually posted and
taken, which is the claim this index needs, and it is one file to read rather than a translation to
re-run. It records the identity of each value and never the value itself: what the payload landed on
is this index's business, and what it landed is the receipt's.

THE COST. The index is built once per drain and only when that drain carries an aggregate payload, so
a tracker-only run reads nothing at all. Building it is one read per `<id>.report.json` in
`forwarded/` - the sidecar alone, never the receipt beside it, so a forwarded receipt costs one file
open rather than two - and a sidecar is parsed straight into the cells it recorded. `forwarded/` grows
without bound, which is exactly why the read is the sidecar alone and why a whole run pays it once
rather than once per receipt: a spool of a few hundred forwarded receipts is read in a small fraction
of the time a single POST to DHIS2 takes, so the index disappears into the network cost of the drain
it serves. Nothing here truncates, and nothing here samples. A spool large enough for the read to be
felt is one where `forwarded/` wants archiving for its own sake, and an index that quietly stopped
reading part of it would answer "no earlier submission" about a value that has one - which is the one
answer this module must never give.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dhis2w_fhir.spool import IMPORT_REPORT_SUFFIX, SpoolLayout, SpoolReadError, SpoolState

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from dhis2w_client.generated.v42.oas import DataValueSet

__all__ = [
    "AggregateCell",
    "ForwardOverwrite",
    "ForwardedCellIndex",
    "ForwardedSubmission",
    "ForwardedValueRecord",
    "OverwrittenValue",
    "aggregate_cells",
    "build_forwarded_cell_index",
]

#: What joins one cell's five keys into the string the index is keyed on. A vertical bar appears in no
#: DHIS2 UID and in no ISO period, so two different cells cannot collide on one key.
_CELL_KEY_SEPARATOR = "|"

#: What a sidecar calls the payload family this index is about, as `ConversionTargetKind` spells it. Read
#: as a string rather than imported, so the reader stays a projection of the file rather than of the enum.
_AGGREGATE_TARGET_KIND = "data-value-set"


class AggregateCell(BaseModel):
    """The full DHIS2 identity of one aggregate data value - the five keys that name exactly one cell."""

    model_config = ConfigDict(frozen=True)

    data_element: str
    category_option_combo: str | None = None
    """Unset where the data element rides the default category combo, which is what DHIS2 files it under."""

    period: str | None = None
    organisation_unit: str | None = None
    attribute_option_combo: str | None = None
    """Unset where the data set rides the default category combo, which is what DHIS2 files it under."""

    @property
    def key(self) -> str:
        """The five keys as the one string an index is keyed on, an unset key included as its absence."""
        return _CELL_KEY_SEPARATOR.join(
            part or ""
            for part in (
                self.data_element,
                self.category_option_combo,
                self.period,
                self.organisation_unit,
                self.attribute_option_combo,
            )
        )

    @property
    def line(self) -> str:
        """The five keys as the one cell a report shows, since a data value has no other name."""
        parts = [
            self.data_element,
            self.category_option_combo,
            self.period,
            self.organisation_unit,
            self.attribute_option_combo,
        ]
        return " / ".join(part for part in parts if part)


class ForwardedSubmission(BaseModel):
    """Which forwarded receipt sent a value, and when that receipt was received."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str = ""
    """Empty where the receipt's envelope recorded no arrival time, which a captured receipt always does."""


class OverwrittenValue(BaseModel):
    """One value a drain sends that a forwarded receipt already sent, and which receipt sent it."""

    model_config = ConfigDict(frozen=True)

    cell: AggregateCell
    previous_response_id: str
    """The receipt that last sent this value, which is the submission whose number the instance holds."""

    previous_received_at: str = ""

    @property
    def line(self) -> str:
        """The value and its earlier submission as the one line a report file and a terminal cell both want."""
        received = f", received {self.previous_received_at}" if self.previous_received_at else ""
        return f"{self.cell.line} (sent by {self.previous_response_id}{received})"


class ForwardOverwrite(BaseModel):
    """Every value one response of a drain sends that an earlier submission had already sent."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    values: tuple[OverwrittenValue, ...] = ()


class ForwardedValueRecord(BaseModel):
    """The part of a forwarded receipt's sidecar this index reads: the cells it landed on, and when it arrived.

    A projection of the sidecar rather than the whole of it, because the index has no use for DHIS2's
    counts, and reading them would tie this module to the report shape the service writes.
    """

    model_config = ConfigDict(extra="ignore")

    received_at: str = ""
    cells: tuple[AggregateCell, ...] = ()
    target_kind: str | None = None


class ForwardedCellIndex(BaseModel):
    """Which forwarded receipt last sent each aggregate value a spool has landed in DHIS2.

    Mutable for the length of one drain: a receipt filed to `forwarded/` mid-run has landed its
    values, so a later receipt of the same run that sends them again replaces them just as surely as
    one from last week does. The run records each payload as DHIS2 takes it, and the answer stays
    true inside the drain as well as across drains.
    """

    covered: dict[str, ForwardedSubmission] = Field(default_factory=dict)
    """The submission that last sent each cell, keyed by `AggregateCell.key`."""

    receipts_read: int = 0
    """How many forwarded sidecars this index read, which is what its cost is counted in."""

    receipts_without_values: int = 0
    """Aggregate receipts in `forwarded/` whose sidecar records no cells, so this index cannot see them."""

    def already_sent(self, cells: Sequence[AggregateCell]) -> tuple[OverwrittenValue, ...]:
        """Every cell of one payload a forwarded receipt already sent, in the order the payload names them."""
        found: list[OverwrittenValue] = []
        for cell in cells:
            submission = self.covered.get(cell.key)
            if submission is not None:
                found.append(
                    OverwrittenValue(
                        cell=cell,
                        previous_response_id=submission.response_id,
                        previous_received_at=submission.received_at,
                    )
                )
        return tuple(found)

    def record(self, cells: Sequence[AggregateCell], submission: ForwardedSubmission) -> None:
        """Record one submission as the sender of these cells, keeping the latest sender of each.

        The receipt named for a cell is the last one to have sent it, because that is the submission
        whose number the instance is holding. Arrival time decides, since `forwarded/` is read in
        file-name order and a receipt id is a random hex string that orders on nothing.
        """
        for cell in cells:
            held = self.covered.get(cell.key)
            if held is None or submission.received_at >= held.received_at:
                self.covered[cell.key] = submission


def aggregate_cells(data_value_set: DataValueSet) -> tuple[AggregateCell, ...]:
    """The full identity of every data value one `/api/dataValueSets` envelope carries.

    A data value may name its own period, organisation unit, and attribute option combo, and DHIS2
    reads the envelope's as the default for the ones it does not - so a cell is read the same way
    round here, the value's own key first and the envelope's behind it.
    """
    return tuple(
        AggregateCell(
            data_element=value.dataElement or "",
            category_option_combo=value.categoryOptionCombo,
            period=value.period or data_value_set.period,
            organisation_unit=value.orgUnit or data_value_set.orgUnit,
            attribute_option_combo=value.attributeOptionCombo or data_value_set.attributeOptionCombo,
        )
        for value in data_value_set.dataValues or []
    )


def build_forwarded_cell_index(layout: SpoolLayout) -> ForwardedCellIndex:
    """Read every forwarded receipt's sidecar into the index of what this spool has already landed.

    Only `forwarded/` counts. A rejected receipt never landed its values, so it covers nothing, and a
    receipt still in the queue has not been sent at all.

    A sidecar that will not read is counted rather than raised: one unreadable file must not cost a
    drain its answer about the other two hundred, and the count is what keeps that silence visible.
    """
    directory = layout.directory_for(SpoolState.FORWARDED)
    if not directory.is_dir():
        return ForwardedCellIndex()
    index = ForwardedCellIndex()
    for path in sorted(_sidecar_paths(directory)):
        index.receipts_read += 1
        record = _read_value_record(path)
        if record is None or not record.cells:
            if record is None or record.target_kind == _AGGREGATE_TARGET_KIND:
                index.receipts_without_values += 1
            continue
        submission = ForwardedSubmission(
            response_id=path.name.removesuffix(IMPORT_REPORT_SUFFIX), received_at=record.received_at
        )
        index.record(record.cells, submission)
    return index


def _sidecar_paths(directory: Path) -> list[Path]:
    """Every import report of one state directory, with the receipts themselves left out."""
    try:
        return [path for path in directory.iterdir() if path.is_file() and path.name.endswith(IMPORT_REPORT_SUFFIX)]
    except OSError as error:
        raise SpoolReadError(f"{directory}: the spool directory cannot be read ({error})") from error


def _read_value_record(path: Path) -> ForwardedValueRecord | None:
    """One sidecar as the record this index reads, or None when the file will not read as one at all."""
    try:
        return ForwardedValueRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None
