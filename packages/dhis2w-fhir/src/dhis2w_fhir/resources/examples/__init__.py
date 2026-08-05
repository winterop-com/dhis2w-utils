"""FSH emission for example responses: one `Usage: #example` QuestionnaireResponse per captured form.

A generated `Questionnaire` says what a DHIS2 form asks; an example response says what an
answer to it looks like. Each one answers its target on the very `linkId`s the questionnaire
defines - section groups nest their questions, and a data element disaggregated by a
non-default category combo nests one child per option combo under `<deUid>.<cocUid>`, which
is exactly the key a DHIS2 data value carries.

Two sources feed the same emission path. `synthetic` (the default) generates the values here
from a seeded RNG, so no data endpoint is called and nothing off the instance is published.
`instance` fills them from the values the server actually holds, which is what makes a demo
IG read like the real thing - and what makes it a deliberate opt-in.

Files land in their own `examples/` sync directory, one per response, so the target sweeps
its own output alone.
"""

from __future__ import annotations

import datetime
import hashlib
import random
import re
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.names import fsh_code, page_text, quote
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.period.parser import parse_period
from dhis2w_fhir.period.recent import recent_periods
from dhis2w_fhir.period.schemas import PeriodValue
from dhis2w_fhir.resources.examples.schemas import (
    MAXIMUM_EXAMPLES_PER_TARGET,
    ExampleAnswerIn,
    ExampleResponseIn,
    ExampleSelection,
    ExampleSource,
)
from dhis2w_fhir.resources.option_sets import concept_assignments, option_set_identity_index
from dhis2w_fhir.resources.option_sets.schemas import (
    ConceptAssignmentPlan,
    OptionIn,
    OptionSetIdentity,
    OptionSetIdentityPlan,
    OptionSetIn,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    FormKind,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
)
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "BOOLEAN_VALUE_TYPES",
    "COMPLETED_STATUS",
    "DECIMAL_VALUE_TYPES",
    "DEFAULT_ANSWER_ELEMENT",
    "EXAMPLES_DIRECTORY",
    "INTEGER_VALUE_TYPES",
    "MAXIMUM_EXAMPLES_PER_TARGET",
    "MULTI_VALUE_TYPE",
    "ORGANISATION_UNIT_VALUE_TYPE",
    "STATUS_BY_EVENT_STATUS",
    "TEMPORAL_ANSWER_ELEMENTS",
    "URI_VALUE_TYPE",
    "ExampleAnswerIn",
    "ExampleResponseIn",
    "ExampleSelection",
    "ExampleSource",
    "SyntheticBuild",
    "answer_element",
    "build_example_artifacts",
    "build_synthetic_responses",
    "response_status_code",
    "zoned_date_time",
]

#: Sync directory holding one QuestionnaireResponse per example.
EXAMPLES_DIRECTORY = "examples"

#: The response status a captured DHIS2 data value set carries - a reported period is complete.
COMPLETED_STATUS = "completed"

#: How a DHIS2 event status reads as a `QuestionnaireResponse.status`. A scheduled, overdue, or
#: visited event has still been captured against the form, so it reads as completed too.
STATUS_BY_EVENT_STATUS = {
    "COMPLETED": COMPLETED_STATUS,
    "ACTIVE": "in-progress",
    "SKIPPED": "stopped",
    "SCHEDULE": COMPLETED_STATUS,
    "OVERDUE": COMPLETED_STATUS,
    "VISITED": COMPLETED_STATUS,
}

#: DHIS2 value types answered as a FHIR integer.
INTEGER_VALUE_TYPES = frozenset({"INTEGER", "INTEGER_POSITIVE", "INTEGER_NEGATIVE", "INTEGER_ZERO_OR_POSITIVE"})

#: DHIS2 value types answered as a FHIR decimal.
DECIMAL_VALUE_TYPES = frozenset({"NUMBER", "PERCENTAGE", "UNIT_INTERVAL"})

#: DHIS2 value types answered as a FHIR boolean.
BOOLEAN_VALUE_TYPES = frozenset({"BOOLEAN", "TRUE_ONLY"})

#: The FHIR answer element each temporal DHIS2 value type takes. `AGE` is a date on the wire -
#: DHIS2 stores the date of birth and renders the age from it.
TEMPORAL_ANSWER_ELEMENTS = {
    "DATE": "valueDate",
    "DATETIME": "valueDateTime",
    "TIME": "valueTime",
    "AGE": "valueDate",
}

#: The answer elements a temporal question lands on, which each normalise their own R4 primitive.
_TEMPORAL_ELEMENTS = frozenset(TEMPORAL_ANSWER_ELEMENTS.values())

#: The DHIS2 value type answered as a FHIR uri.
URI_VALUE_TYPE = "URL"

#: The DHIS2 value type holding several option codes in one comma-separated wire value.
MULTI_VALUE_TYPE = "MULTI_TEXT"

#: The separator DHIS2 joins a MULTI_TEXT value's option codes with.
_MULTI_VALUE_SEPARATOR = ","

#: The value types an example leaves unanswered. An attachment or a geometry blob says nothing
#: useful when it is invented, and inventing one would misrepresent the form. `REFERENCE` and
#: `TRACKER_ASSOCIATE` point at DHIS2 objects the IG publishes no FHIR resource for, so an
#: answer would name a target no consumer can resolve.
_UNSYNTHESIZABLE_VALUE_TYPES = frozenset({"FILE_RESOURCE", "IMAGE", "GEOJSON", "REFERENCE", "TRACKER_ASSOCIATE"})

#: The DHIS2 value type answered as a reference to the organisation unit's Location instance.
ORGANISATION_UNIT_VALUE_TYPE = "ORGANISATION_UNIT"

# The R4 primitive patterns (https://hl7.org/fhir/R4/datatypes.html#primitive) the temporal
# answers are lexically checked against. They are stricter than what DHIS2 stores, and they are
# only the shape: `2026-99-99` and `25:99:99` match them, so every temporal answer clears the
# calendar and the clock as well before it is emitted.
_FHIR_DATE_PATTERN = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_FHIR_DATE_TIME_PATTERN = re.compile(r"^\d{4}(-\d{2}(-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2}))?)?)?$")
_FHIR_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}(\.\d+)?$")

#: How many dash-separated parts a year-only and a year-month R4 date carry.
_YEAR_ONLY_DATE_PARTS = 1
_YEAR_MONTH_DATE_PARTS = 2

#: The month numbers a year-month R4 date may name.
_FIRST_MONTH = 1
_LAST_MONTH = 12

#: The UTC offsets an R4 dateTime may carry. The stdlib accepts anything under a full day, so
#: the real-world span is enforced here: no zone sits west of -12:00 or east of +14:00.
_EARLIEST_UTC_OFFSET = datetime.timedelta(hours=-12)
_LATEST_UTC_OFFSET = datetime.timedelta(hours=14)

# The plain decimal and integer forms an FSH numeric literal may take. They are deliberately
# narrower than what `float()` and `int()` accept: FSH writes a numeric answer unquoted, so
# `NaN`, `Infinity`, and an exponent (`1e3`) are not numbers a FHIR primitive can carry, a
# leading `+` or a leading zero (`01.5`) is not the canonical lexical form, and `int()` would
# additionally read the underscores and surrounding whitespace of `1_0` as ten. A value that
# does not match is answered as a string rather than emitted as an invalid literal.
_FSH_DECIMAL_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
_FSH_INTEGER_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)$")

#: The zone FHIR requires on a dateTime that carries a time, and DHIS2 leaves off (BUGS.md #62).
_ASSUMED_ZONE = "Z"

#: How many colon-separated parts a bare `HH:MM` time has, before FHIR's mandatory seconds.
_MINUTE_ONLY_TIME_PARTS = 2

#: What an example declares when a response profile's 1..1 element (D2Period, authored) is missing.
_BASE_RESPONSE_RESOURCE = "QuestionnaireResponse"

#: The DHIS2 wire spellings of a true and a false boolean value.
_TRUE_LITERALS = frozenset({"true", "1"})
_FALSE_LITERALS = frozenset({"false", "0"})

#: The answer element everything unmapped - and everything that will not cast - falls back to.
DEFAULT_ANSWER_ELEMENT = "valueString"

#: How many days back a synthetic event may have occurred.
_SYNTHETIC_EVENT_WINDOW_DAYS = 30

#: Bytes of the seed digest fed to the synthetic RNG - eight is a full 64-bit seed.
_SEED_BYTES = 8

#: The host a synthetic URL points at - `.invalid` is reserved by RFC 2606 and resolves nowhere.
_SYNTHETIC_URL_HOST = "https://example.invalid"

#: The birth-date range a synthetic `AGE` answer is drawn from.
_SYNTHETIC_AGE_EARLIEST = datetime.date(1950, 1, 1)
_SYNTHETIC_AGE_LATEST = datetime.date(2015, 12, 31)

#: The bounds and precision of a synthetic `COORDINATE` answer's `[longitude,latitude]` pair.
_SYNTHETIC_LONGITUDE_BOUND = 180.0
_SYNTHETIC_LATITUDE_BOUND = 90.0
_SYNTHETIC_COORDINATE_PLACES = 4

#: How many distinct options a synthetic MULTI_TEXT answer selects, when the set holds that many.
_SYNTHETIC_MULTI_SELECTIONS = 2

#: The bounds the synthetic numeric value types draw from.
_SYNTHETIC_INTEGER_BOUND = 1000
_SYNTHETIC_PERCENTAGE_BOUND = 100.0
_SYNTHETIC_DECIMAL_PLACES = 1
_SYNTHETIC_UNIT_INTERVAL_PLACES = 2
_HOURS_PER_DAY = 24

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.examples", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def response_status_code(event_status: str | None) -> str:
    """The `QuestionnaireResponse.status` one DHIS2 event status maps onto, defaulting to completed."""
    if event_status is None:
        return COMPLETED_STATUS
    return STATUS_BY_EVENT_STATUS.get(event_status.upper(), COMPLETED_STATUS)


class _PeriodExtensionView(BaseModel):
    """The D2Period extension of one example: its slice name and the three facts it carries."""

    model_config = ConfigDict(frozen=True)

    extension: str
    iso: str
    period_type: str
    start_date: datetime.date
    end_date: datetime.date


class _Answer(BaseModel):
    """One typed FHIR answer: the `value[x]` element it lands on and its rendered FSH literal."""

    model_config = ConfigDict(frozen=True)

    element: str
    literal: str


class _ItemView(BaseModel):
    """One emitted response item, its FSH soft-index paths and its typed answers already resolved."""

    model_config = ConfigDict(frozen=True)

    new_path: str
    path: str
    link_id: str
    answers: list[_Answer] = Field(default_factory=list)


class _ExampleView(BaseModel):
    """Everything the QuestionnaireResponse template needs for one example, every conditional resolved."""

    model_config = ConfigDict(frozen=True)

    instance_id: str
    instance_of: str
    questionnaire_url: str
    title_literal: str
    description_literal: str
    form_type_extension: str
    form_type_code: FormKind
    organisation_unit_uid: str
    status_code: str
    period: _PeriodExtensionView | None = None
    authored: str | None = None
    items: list[_ItemView] = Field(default_factory=list)


class _ExampleTally(BaseModel):
    """Per-run tally of the example outcomes worth a note: skipped values and typing fall-backs."""

    unknown_data_elements: list[str] = Field(default_factory=list)
    untyped_values: list[str] = Field(default_factory=list)
    uncoded_options: list[str] = Field(default_factory=list)
    periodless_data_sets: list[str] = Field(default_factory=list)
    unauthored_responses: list[str] = Field(default_factory=list)

    def to_notes(self) -> list[str]:
        """Roll the tally up into one aggregate note per noteworthy example outcome."""
        notes: list[str] = []
        if self.unknown_data_elements:
            notes.append(
                aggregate_note(
                    f"{len(self.unknown_data_elements)} captured values reference data elements the "
                    "questionnaire does not ask for; skipped",
                    self.unknown_data_elements,
                )
            )
        if self.untyped_values:
            notes.append(
                aggregate_note(
                    f"{len(self.untyped_values)} example answers could not be cast to their FHIR type; "
                    "answered as strings",
                    self.untyped_values,
                )
            )
        if self.uncoded_options:
            notes.append(
                aggregate_note(
                    f"{len(self.uncoded_options)} example answers select an option the CodeSystem holds no "
                    "concept for; left unanswered",
                    self.uncoded_options,
                )
            )
        if self.periodless_data_sets:
            notes.append(
                aggregate_note(
                    f"{len(self.periodless_data_sets)} data sets have no resolvable reporting period; "
                    "their examples carry no D2Period extension and declare the base QuestionnaireResponse "
                    "instead of the aggregate response profile",
                    self.periodless_data_sets,
                )
            )
        if self.unauthored_responses:
            notes.append(
                aggregate_note(
                    f"{len(self.unauthored_responses)} examples carry an occurrence timestamp FHIR cannot "
                    "express as a dateTime; authored omitted and the base QuestionnaireResponse declared "
                    "instead of the event response profile",
                    self.unauthored_responses,
                )
            )
        return notes


def build_example_artifacts(
    sources: list[QuestionnaireSourceIn],
    responses: list[ExampleResponseIn],
    option_sets: list[OptionSetIn],
    config: GenerateConfig,
    canonical: str,
    *,
    option_set_plan: OptionSetIdentityPlan,
) -> FshBuild:
    """Build one `examples/<targetUid>-<n>.fsh` QuestionnaireResponse per example response.

    `option_set_plan` is the identity plan the terminology target emits from, so a coded answer
    names the CodeSystem the same run writes under either naming source. The concept codes come
    from `concept_assignments`, once per set, for the same reason: an answer names a concept the
    terminology target really wrote, fall-backs and all.
    """
    build = FshBuild()
    foundation = FoundationNaming.from_naming(config.naming)
    index = option_set_identity_index(option_set_plan, _bound_option_set_uids(sources), config)
    sources_by_uid = {source.uid: source for source in sources}
    option_sets_by_uid = {option_set.uid: option_set for option_set in option_sets}
    assignments = _concept_assignments_by_set(option_sets, config)
    template = _ENVIRONMENT.get_template("questionnaire-response.fsh.jinja")
    tally = _ExampleTally()
    ordinals: dict[str, int] = {}
    for response in responses:
        source = sources_by_uid.get(response.target_uid)
        if source is None:
            continue
        ordinal = ordinals.get(response.target_uid, 0) + 1
        ordinals[response.target_uid] = ordinal
        view = _example_view(
            response, source, option_sets_by_uid, assignments, index.identities, foundation, canonical, tally
        )
        build.artifacts.append(
            FshArtifact(
                relative_path=f"{EXAMPLES_DIRECTORY}/{response.target_uid}-{ordinal}.fsh",
                kind="instances",
                fsh_name=f"QuestionnaireResponse-{response.instance_id}",
                content=template.render(example=view),
            )
        )
    build.notes.extend(tally.to_notes())
    if index.unplanned_uids:
        build.notes.append(
            aggregate_note(
                f"{len(index.unplanned_uids)} option sets a question binds are absent from the option-set "
                "selection; their answer coding systems are derived from the UID",
                index.unplanned_uids,
            )
        )
    return build


def _bound_option_set_uids(sources: list[QuestionnaireSourceIn]) -> list[str]:
    """Every option set the given forms bind a question to."""
    return [item.option_set_uid for source in sources for item in _source_items(source) if item.option_set_uid]


def _concept_assignments_by_set(
    option_sets: list[OptionSetIn], config: GenerateConfig
) -> dict[str, ConceptAssignmentPlan]:
    """Run the shared concept-code assignment once per option set, indexed by UID.

    The notes each plan raises stay on the plan and go unread here: a UID fall-back is a fact
    about the CodeSystem, so the terminology target reports it, and the examples target reports
    only what it alone sees - an answer whose option received no concept code.
    """
    return {option_set.uid: concept_assignments(option_set, config) for option_set in option_sets}


class SyntheticBuild(BaseModel):
    """Result of generating synthetic responses: the responses plus what generation could not answer."""

    responses: list[ExampleResponseIn] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def build_synthetic_responses(
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn],
    per_target: int,
    organisation_unit_uid: str,
    today: datetime.date,
) -> SyntheticBuild:
    """Generate `per_target` deterministic example responses per target, answering every question it can.

    The seed is the leading 64 bits of `sha256("<targetUid>:<n>")`, so the values are stable
    across runs, machines, and interpreter restarts - unlike Python's salted `hash`. Only the
    period-anchored values move, because the newest completed period moves with the calendar.
    """
    build = SyntheticBuild()
    option_sets_by_uid = {option_set.uid: option_set for option_set in option_sets}
    unanswerable: list[str] = []
    for source in sorted(sources, key=lambda item: (item.name, item.uid)):
        for ordinal in range(1, per_target + 1):
            build.responses.append(
                _synthetic_response(source, option_sets_by_uid, ordinal, organisation_unit_uid, today, unanswerable)
            )
    if unanswerable:
        build.notes.append(
            aggregate_note(
                f"{len(unanswerable)} questions take an attachment, a geometry document, or a reference to a "
                "DHIS2 object the IG does not publish; left unanswered in the synthetic examples",
                sorted(set(unanswerable)),
            )
        )
    return build


def _synthetic_response(
    source: QuestionnaireSourceIn,
    option_sets_by_uid: dict[str, OptionSetIn],
    ordinal: int,
    organisation_unit_uid: str,
    today: datetime.date,
    unanswerable: list[str],
) -> ExampleResponseIn:
    """Generate one target's `n`-th example: its period or occurrence, then an answer per question."""
    generator = random.Random(_seed(source.uid, ordinal))  # noqa: S311 - illustrative values, not a secret
    period = _synthetic_period(source, today)
    window = _SyntheticWindow.of_period(period) if period is not None else _SyntheticWindow.recent(today)
    instance_id = f"{source.uid}-example-{ordinal}"
    authored: str | None = None
    if source.kind == "event":
        authored = f"{window.pick_date(generator).isoformat()}T{_pick_hour(generator)}:00:00Z"
    answers: list[ExampleAnswerIn] = []
    for key in _answerable_keys(source):
        option_set = option_sets_by_uid.get(key.item.option_set_uid or "")
        value = _synthetic_value(key.item, option_set, generator, window, instance_id, organisation_unit_uid)
        if value is None:
            unanswerable.append(f"{key.item.name} ({key.item.uid})")
            continue
        answers.append(
            ExampleAnswerIn(
                data_element_uid=key.item.uid,
                category_option_combo_uid=key.category_option_combo_uid,
                value=value,
            )
        )
    return ExampleResponseIn(
        instance_id=instance_id,
        target_uid=source.uid,
        kind=source.kind,
        organisation_unit_uid=organisation_unit_uid,
        status_code=COMPLETED_STATUS,
        period=period,
        authored=authored,
        answers=answers,
    )


def _seed(target_uid: str, ordinal: int) -> int:
    """The RNG seed for one target's `n`-th example: the leading 64 bits of a SHA-256 digest."""
    digest = hashlib.sha256(f"{target_uid}:{ordinal}".encode()).digest()
    return int.from_bytes(digest[:_SEED_BYTES], "big")


def _synthetic_period(source: QuestionnaireSourceIn, today: datetime.date) -> PeriodValue | None:
    """The newest completed period of a data set's period type; None for an event program."""
    if source.kind != "aggregate" or not source.period_type:
        return None
    isos = recent_periods(source.period_type, 1, today)
    return parse_period(isos[0]) if isos else None


class _SyntheticWindow(BaseModel):
    """The date range a synthetic temporal value is drawn from."""

    model_config = ConfigDict(frozen=True)

    start_date: datetime.date
    end_date: datetime.date

    @classmethod
    def of_period(cls, period: PeriodValue) -> _SyntheticWindow:
        """The window one reporting period covers."""
        return cls(start_date=period.start_date, end_date=period.end_date)

    @classmethod
    def recent(cls, today: datetime.date) -> _SyntheticWindow:
        """The thirty days before `today`, which is where an event without a period sits."""
        return cls(start_date=today - datetime.timedelta(days=_SYNTHETIC_EVENT_WINDOW_DAYS), end_date=today)

    def pick_date(self, generator: random.Random) -> datetime.date:
        """A seeded day inside the window, its last day excluded so the value is already past."""
        span = max((self.end_date - self.start_date).days, 1)
        return self.start_date + datetime.timedelta(days=generator.randrange(span))


def _pick_hour(generator: random.Random) -> str:
    """A seeded two-digit hour - synthetic times land on the hour."""
    return f"{generator.randrange(_HOURS_PER_DAY):02d}"


def _synthetic_value(
    item: QuestionnaireItemIn,
    option_set: OptionSetIn | None,
    generator: random.Random,
    window: _SyntheticWindow,
    instance_id: str,
    organisation_unit_uid: str,
) -> str | None:
    """Generate one DHIS2-shaped value string for a question; None when the type is not worth faking."""
    value_type = item.value_type
    if value_type in _UNSYNTHESIZABLE_VALUE_TYPES:
        return None
    if item.option_set_uid is not None and option_set is not None and option_set.options:
        return _synthetic_option_value(value_type, option_set, generator)
    if value_type == ORGANISATION_UNIT_VALUE_TYPE:
        return organisation_unit_uid
    if value_type in INTEGER_VALUE_TYPES:
        return str(generator.randrange(_SYNTHETIC_INTEGER_BOUND))
    if value_type == "UNIT_INTERVAL":
        return str(round(generator.uniform(0, 1), _SYNTHETIC_UNIT_INTERVAL_PLACES))
    if value_type in DECIMAL_VALUE_TYPES:
        return str(round(generator.uniform(0, _SYNTHETIC_PERCENTAGE_BOUND), _SYNTHETIC_DECIMAL_PLACES))
    if value_type == "TRUE_ONLY":
        return "true"
    if value_type == "BOOLEAN":
        return "true" if generator.randrange(2) else "false"
    if value_type == "DATE":
        return window.pick_date(generator).isoformat()
    if value_type == "DATETIME":
        return f"{window.pick_date(generator).isoformat()}T{_pick_hour(generator)}:00:00Z"
    if value_type == "TIME":
        return f"{_pick_hour(generator)}:00:00"
    if value_type == "AGE":
        return _seeded_birth_date(generator).isoformat()
    if value_type == URI_VALUE_TYPE:
        return f"{_SYNTHETIC_URL_HOST}/{instance_id}"
    if value_type == "COORDINATE":
        return _seeded_coordinate(generator)
    return f"Example {item.name}"


def _synthetic_option_value(value_type: str, option_set: OptionSetIn, generator: random.Random) -> str:
    """Pick one option's stored value, or the comma-joined pair a MULTI_TEXT question captures."""
    stored = [option.code or option.uid for option in option_set.options]
    if value_type != MULTI_VALUE_TYPE:
        return stored[generator.randrange(len(stored))]
    wanted = min(_SYNTHETIC_MULTI_SELECTIONS, len(stored))
    return _MULTI_VALUE_SEPARATOR.join(generator.sample(stored, wanted))


def _seeded_birth_date(generator: random.Random) -> datetime.date:
    """A seeded date of birth - what DHIS2 stores behind an `AGE` question."""
    span = (_SYNTHETIC_AGE_LATEST - _SYNTHETIC_AGE_EARLIEST).days
    return _SYNTHETIC_AGE_EARLIEST + datetime.timedelta(days=generator.randrange(span))


def _seeded_coordinate(generator: random.Random) -> str:
    """A seeded `[longitude,latitude]` pair in the DHIS2 COORDINATE wire spelling."""
    places = _SYNTHETIC_COORDINATE_PLACES
    longitude = round(generator.uniform(-_SYNTHETIC_LONGITUDE_BOUND, _SYNTHETIC_LONGITUDE_BOUND), places)
    latitude = round(generator.uniform(-_SYNTHETIC_LATITUDE_BOUND, _SYNTHETIC_LATITUDE_BOUND), places)
    return f"[{longitude},{latitude}]"


class _AnswerableKey(BaseModel):
    """One question a response can answer: its data element, and the option combo when disaggregated."""

    model_config = ConfigDict(frozen=True)

    item: QuestionnaireItemIn
    category_option_combo_uid: str | None = None


def _answerable_keys(source: QuestionnaireSourceIn) -> list[_AnswerableKey]:
    """Every question of one form in structure order, one entry per option combo where disaggregated."""
    keys: list[_AnswerableKey] = []
    for item in _source_items(source):
        if _is_disaggregated(item) and item.category_combo is not None:
            keys.extend(
                _AnswerableKey(item=item, category_option_combo_uid=option_combo.uid)
                for option_combo in item.category_combo.option_combos
            )
        else:
            keys.append(_AnswerableKey(item=item))
    return keys


def _source_items(source: QuestionnaireSourceIn) -> list[QuestionnaireItemIn]:
    """Every question one form carries, sectioned first and in the order the questionnaire emits them."""
    return [item for section in source.sections for item in section.items] + list(source.flat_items)


def _is_disaggregated(item: QuestionnaireItemIn) -> bool:
    """Check whether a data element carries a real (non-default) category combo."""
    return item.category_combo is not None and not item.category_combo.is_default


def _example_view(
    response: ExampleResponseIn,
    source: QuestionnaireSourceIn,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    identities: dict[str, OptionSetIdentity],
    foundation: FoundationNaming,
    canonical: str,
    tally: _ExampleTally,
) -> _ExampleView:
    """Project one example response onto the view the QuestionnaireResponse template renders."""
    label = "data set" if source.kind == "aggregate" else "event program"
    period: _PeriodExtensionView | None = None
    if response.period is not None:
        period = _PeriodExtensionView(
            extension=foundation.period_extension,
            iso=response.period.iso,
            period_type=response.period.period_type,
            start_date=response.period.start_date,
            end_date=response.period.end_date,
        )
    elif source.kind == "aggregate":
        tally.periodless_data_sets.append(f"{source.name} ({source.uid})")
    answers = _answers_by_link_id(response, source, option_sets_by_uid, assignments, identities, tally)
    authored = _authored(response, tally)
    return _ExampleView(
        instance_id=response.instance_id,
        instance_of=_response_profile(source.kind, foundation, period=period, authored=authored),
        questionnaire_url=f"{canonical}/Questionnaire/{source.uid}",
        title_literal=page_text(f"Example response - {source.name}"),
        description_literal=page_text(
            f"Example QuestionnaireResponse against the DHIS2 {label} {source.name} ({source.uid})."
        ),
        form_type_extension=foundation.form_type_extension,
        form_type_code=source.kind,
        organisation_unit_uid=response.organisation_unit_uid,
        status_code=response.status_code,
        period=period,
        authored=authored,
        items=_item_views(source, answers),
    )


def _response_profile(
    kind: FormKind,
    foundation: FoundationNaming,
    *,
    period: _PeriodExtensionView | None,
    authored: str | None,
) -> str:
    """The declared instance type: the kind's response profile, or the base resource when a 1..1 element is missing."""
    if kind == "aggregate":
        return foundation.aggregate_response_profile if period is not None else _BASE_RESPONSE_RESOURCE
    return foundation.event_response_profile if authored is not None else _BASE_RESPONSE_RESOURCE


def _authored(response: ExampleResponseIn, tally: _ExampleTally) -> str | None:
    """The response's authoring timestamp as an R4 dateTime, dropped and tallied when it is not one."""
    if response.authored is None:
        return None
    normalized = zoned_date_time(response.authored.strip())
    if _is_fhir_date_time(normalized):
        return normalized
    tally.unauthored_responses.append(f"{response.instance_id} = {response.authored!r}")
    return None


def _answers_by_link_id(
    response: ExampleResponseIn,
    source: QuestionnaireSourceIn,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    identities: dict[str, OptionSetIdentity],
    tally: _ExampleTally,
) -> dict[str, list[_Answer]]:
    """Type every captured value and index it by the questionnaire `linkId` it answers."""
    items_by_uid = {item.uid: item for item in _source_items(source)}
    answers: dict[str, list[_Answer]] = {}
    for captured in response.answers:
        item = items_by_uid.get(captured.data_element_uid)
        if item is None:
            tally.unknown_data_elements.append(f"{captured.data_element_uid} in {response.instance_id}")
            continue
        link_id = captured.data_element_uid
        if _is_disaggregated(item) and captured.category_option_combo_uid is not None:
            link_id = f"{link_id}.{captured.category_option_combo_uid}"
        answers[link_id] = _typed_answers(item, captured.value, option_sets_by_uid, assignments, identities, tally)
    return answers


def _typed_answers(
    item: QuestionnaireItemIn,
    value: str,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    identities: dict[str, OptionSetIdentity],
    tally: _ExampleTally,
) -> list[_Answer]:
    """Cast one captured value onto the FHIR answer type its value type asks for - several for MULTI_TEXT."""
    if item.option_set_uid is not None:
        selected = value.split(_MULTI_VALUE_SEPARATOR) if item.value_type == MULTI_VALUE_TYPE else [value]
        coded = [
            _coded_answer(item, item.option_set_uid, part.strip(), option_sets_by_uid, assignments, identities, tally)
            for part in selected
        ]
        return [answer for answer in coded if answer is not None]
    return [_typed_answer(item, value, tally)]


def answer_element(value_type: str) -> str:
    """The FHIR `value[x]` element one DHIS2 value type answers on, when the question binds no option set.

    An option-set-bound question answers as a `valueCoding` into that set's CodeSystem whatever
    its value type, so this is the typing of everything else - and the single table the capture
    page documents the contract from.
    """
    if value_type in INTEGER_VALUE_TYPES:
        return "valueInteger"
    if value_type in DECIMAL_VALUE_TYPES:
        return "valueDecimal"
    if value_type in BOOLEAN_VALUE_TYPES:
        return "valueBoolean"
    temporal = TEMPORAL_ANSWER_ELEMENTS.get(value_type)
    if temporal is not None:
        return temporal
    if value_type == URI_VALUE_TYPE:
        return "valueUri"
    if value_type == ORGANISATION_UNIT_VALUE_TYPE:
        return "valueReference"
    return DEFAULT_ANSWER_ELEMENT


def _typed_answer(item: QuestionnaireItemIn, value: str, tally: _ExampleTally) -> _Answer:
    """Cast one DHIS2 value string onto the FHIR answer type its data element's value type asks for."""
    text = value.strip()
    element = answer_element(item.value_type)
    if element == "valueInteger":
        return _integer_answer(item, text, tally)
    if element == "valueDecimal":
        return _decimal_answer(item, text, tally)
    if element == "valueBoolean":
        return _boolean_answer(item, text, tally)
    if element in _TEMPORAL_ELEMENTS:
        return _temporal_answer(item, text, element, tally)
    if element == "valueUri":
        return _Answer(element=element, literal=quote(text))
    if element == "valueReference":
        return _Answer(element=element, literal=f"Reference(Location/{text})")
    return _Answer(element=DEFAULT_ANSWER_ELEMENT, literal=quote(value))


def _temporal_answer(item: QuestionnaireItemIn, text: str, element: str, tally: _ExampleTally) -> _Answer:
    """Answer a date / dateTime / time question, normalising DHIS2's spelling into the R4 primitive."""
    if element == "valueDate":
        normalized = text.partition("T")[0]
        valid = _is_fhir_date(normalized)
    elif element == "valueDateTime":
        normalized = zoned_date_time(text)
        valid = _is_fhir_date_time(normalized)
    else:
        normalized = _seconds_precision(text)
        valid = _is_fhir_time(normalized)
    if not valid:
        return _fallback(item, text, tally)
    return _Answer(element=element, literal=quote(normalized))


def _is_fhir_date(value: str) -> bool:
    """Check an R4 `date`: the lexical shape, then the calendar at whatever precision it carries."""
    return bool(_FHIR_DATE_PATTERN.match(value)) and _is_calendar_date(value)


def _is_fhir_time(value: str) -> bool:
    """Check an R4 `time`: the lexical shape, then a real reading of the clock (`24:00:00` is not one)."""
    if not _FHIR_TIME_PATTERN.match(value):
        return False
    try:
        datetime.time.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_fhir_date_time(value: str) -> bool:
    """Check an R4 `dateTime`: the lexical shape, then a real instant inside the offsets R4 allows.

    A date-only dateTime is exactly an R4 date, so it clears the calendar the same way. A value
    carrying a time clears the calendar, the clock, and the zone in one parse, and then its
    offset is bounded, which the stdlib leaves open all the way to a full day either side.
    """
    if not _FHIR_DATE_TIME_PATTERN.match(value):
        return False
    if "T" not in value:
        return _is_calendar_date(value)
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return offset is not None and _EARLIEST_UTC_OFFSET <= offset <= _LATEST_UTC_OFFSET


def _is_calendar_date(value: str) -> bool:
    """Check a lexically valid R4 date against the calendar: a bare year passes, a month must exist."""
    parts = value.split("-")
    if len(parts) == _YEAR_ONLY_DATE_PARTS:
        return True
    if len(parts) == _YEAR_MONTH_DATE_PARTS:
        return _FIRST_MONTH <= int(parts[1]) <= _LAST_MONTH
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def zoned_date_time(value: str) -> str:
    """Give a DHIS2 timestamp the UTC zone R4 requires whenever it carries a time but no offset.

    DHIS2 serves `occurredAt` and `DATETIME` data values as zone-less local timestamps
    (`2025-12-30T00:00:00.000`) under fields its OpenAPI types as `Instant`, and an R4
    `dateTime` carrying a time must carry an offset. See BUGS.md #62.
    """
    _, separator, time_part = value.partition("T")
    if not separator or time_part.endswith(("Z", "z")) or "+" in time_part or "-" in time_part:
        return value
    return f"{value}{_ASSUMED_ZONE}"


def _seconds_precision(value: str) -> str:
    """Give a bare `HH:MM` the seconds R4 `time` makes mandatory."""
    return f"{value}:00" if len(value.split(":")) == _MINUTE_ONLY_TIME_PARTS else value


def _integer_answer(item: QuestionnaireItemIn, text: str, tally: _ExampleTally) -> _Answer:
    """Answer an integer question, falling back to a string when the stored value is not a plain integer."""
    if not _FSH_INTEGER_PATTERN.match(text):
        return _fallback(item, text, tally)
    return _Answer(element="valueInteger", literal=str(int(text)))


def _decimal_answer(item: QuestionnaireItemIn, text: str, tally: _ExampleTally) -> _Answer:
    """Answer a decimal question, keeping the stored precision but refusing what is not a plain decimal."""
    if not _FSH_DECIMAL_PATTERN.match(text):
        return _fallback(item, text, tally)
    return _Answer(element="valueDecimal", literal=text)


def _boolean_answer(item: QuestionnaireItemIn, text: str, tally: _ExampleTally) -> _Answer:
    """Answer a boolean question from DHIS2's `true`/`false` (or `1`/`0`) spellings."""
    lowered = text.lower()
    if lowered in _TRUE_LITERALS:
        return _Answer(element="valueBoolean", literal="true")
    if lowered in _FALSE_LITERALS:
        return _Answer(element="valueBoolean", literal="false")
    return _fallback(item, text, tally)


def _coded_answer(
    item: QuestionnaireItemIn,
    option_set_uid: str,
    value: str,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    identities: dict[str, OptionSetIdentity],
    tally: _ExampleTally,
) -> _Answer | None:
    """Answer an option-set question as a Coding into that set's CodeSystem.

    A value that maps to no option of the set is answered as a plain string. A value whose
    option received no concept code is not answered at all: the CodeSystem holds nothing to
    point at, so the answer is dropped and tallied rather than emitted as a dangling coding.
    """
    option_set = option_sets_by_uid.get(option_set_uid)
    option = _option_for(option_set, value) if option_set is not None else None
    if option_set is None or option is None:
        return _fallback(item, value, tally)
    plan = assignments.get(option_set_uid)
    concept_code = plan.code_for(option.uid) if plan is not None else None
    if concept_code is None:
        tally.uncoded_options.append(f"{option.uid} in {option_set.name} ({option_set.uid})")
        return None
    system = identities[option_set_uid].code_system_name
    return _Answer(element="valueCoding", literal=f"{system}{fsh_code(concept_code)} {quote(option.name)}")


def _option_for(option_set: OptionSetIn, value: str) -> OptionIn | None:
    """Resolve a stored DHIS2 value to its option - by code, which is what a data value holds, then by UID."""
    by_code = next((option for option in option_set.options if option.code == value), None)
    if by_code is not None:
        return by_code
    return next((option for option in option_set.options if option.uid == value), None)


def _fallback(item: QuestionnaireItemIn, value: str, tally: _ExampleTally) -> _Answer:
    """Answer as a plain string and tally why, so a run says how much it could not type."""
    tally.untyped_values.append(f"{item.name} ({item.uid}) = {value!r}")
    return _Answer(element=DEFAULT_ANSWER_ELEMENT, literal=quote(value))


def _item_views(source: QuestionnaireSourceIn, answers: dict[str, list[_Answer]]) -> list[_ItemView]:
    """Mirror the questionnaire's item tree, keeping only the branches an answer reaches."""
    views: list[_ItemView] = []
    for section in source.sections:
        nested = [view for item in section.items for view in _data_element_views(item, answers, depth=1)]
        if not nested:
            continue
        views.append(_ItemView(new_path=_new_path(0), path=_set_path(0), link_id=section.uid))
        views.extend(nested)
    for item in source.flat_items:
        views.extend(_data_element_views(item, answers, depth=0))
    return views


def _data_element_views(item: QuestionnaireItemIn, answers: dict[str, list[_Answer]], depth: int) -> list[_ItemView]:
    """Build one data element's response items: an answered question, or a group of option combos."""
    if _is_disaggregated(item) and item.category_combo is not None:
        children = [
            _answered_view(f"{item.uid}.{option_combo.uid}", answers[f"{item.uid}.{option_combo.uid}"], depth + 1)
            for option_combo in item.category_combo.option_combos
            if f"{item.uid}.{option_combo.uid}" in answers
        ]
        if children:
            group = _ItemView(new_path=_new_path(depth), path=_set_path(depth), link_id=item.uid)
            return [group, *children]
    answered = answers.get(item.uid)
    return [_answered_view(item.uid, answered, depth)] if answered else []


def _answered_view(link_id: str, answers: list[_Answer], depth: int) -> _ItemView:
    """One response item carrying its typed answers - several only where the question repeats."""
    return _ItemView(new_path=_new_path(depth), path=_set_path(depth), link_id=link_id, answers=answers)


def _new_path(depth: int) -> str:
    """The FSH path that opens a new item at `depth` (e.g. `item[=].item[+]`)."""
    return f"{'item[=].' * depth}item[+]"


def _set_path(depth: int) -> str:
    """The FSH path that addresses the item just opened at `depth` (e.g. `item[=].item[=]`)."""
    return f"{'item[=].' * depth}item[=]"
