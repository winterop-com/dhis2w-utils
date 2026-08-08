"""FSH emission for example responses: one `Usage: #example` QuestionnaireResponse per captured form.

A generated `Questionnaire` says what a DHIS2 form asks; an example response says what an
answer to it looks like. Each one answers its target on the very `linkId`s the questionnaire
defines - section groups nest their questions, and a data set's data element disaggregated by
a non-default category combo nests one child per option combo under `<deUid>.<cocUid>`, which
is exactly the key a DHIS2 data value carries. The disaggregation rule is the questionnaire
emitter's own `is_disaggregated`, so an event-kind response answers the flat `<deUid>` however
its data element is categorised - an event data value has no categoryOptionCombo slot on the
wire, and an example must not answer a question its own form does not ask.

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
import string
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.names import fsh_code, page_text, quote
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.period.parser import parse_period
from dhis2w_fhir.period.recent import recent_periods
from dhis2w_fhir.period.schemas import PeriodValue
from dhis2w_fhir.r4.primitives import (
    is_fhir_date,
    is_fhir_date_time,
    is_fhir_time,
    seconds_precision,
    zoned_date_time,
)
from dhis2w_fhir.resources.examples.schemas import (
    MAXIMUM_EXAMPLES_PER_TARGET,
    ExampleAnswer,
    ExampleAnswerIn,
    ExampleAnswerRules,
    ExampleCoding,
    ExampleItem,
    ExampleResponseIn,
    ExampleSelection,
    ExampleSource,
    ExampleTrackerContext,
)
from dhis2w_fhir.resources.option_sets import concept_assignments, option_set_identity_index
from dhis2w_fhir.resources.option_sets.schemas import (
    ConceptAssignmentPlan,
    OptionIn,
    OptionSetIdentity,
    OptionSetIdentityPlan,
    OptionSetIn,
)
from dhis2w_fhir.resources.questionnaires import bound_option_set_uids, is_disaggregated, source_items
from dhis2w_fhir.resources.questionnaires.schemas import (
    FormKind,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    source_display_name,
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
    "MULTI_VALUE_SEPARATOR",
    "MULTI_VALUE_TYPE",
    "ORGANISATION_UNIT_VALUE_TYPE",
    "STATUS_BY_EVENT_STATUS",
    "TEMPORAL_ANSWER_ELEMENTS",
    "URI_VALUE_TYPE",
    "ExampleAnswer",
    "ExampleAnswerIn",
    "ExampleAnswerRules",
    "ExampleCoding",
    "ExampleItem",
    "ExampleResponseIn",
    "ExampleSelection",
    "ExampleSource",
    "ExampleTally",
    "ExampleTrackerContext",
    "SyntheticBuild",
    "answer_element",
    "build_example_artifacts",
    "build_synthetic_responses",
    "example_answers",
    "example_authored",
    "example_concept_assignments",
    "example_is_complete",
    "example_items",
    "example_period",
    "example_tracker_context",
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
MULTI_VALUE_SEPARATOR = ","

#: The value types an example leaves unanswered. An attachment or a geometry blob says nothing
#: useful when it is invented, and inventing one would misrepresent the form. `REFERENCE` and
#: `TRACKER_ASSOCIATE` point at DHIS2 objects the IG publishes no FHIR resource for, so an
#: answer would name a target no consumer can resolve.
_UNSYNTHESIZABLE_VALUE_TYPES = frozenset({"FILE_RESOURCE", "IMAGE", "GEOJSON", "REFERENCE", "TRACKER_ASSOCIATE"})

#: The DHIS2 value type answered as a reference to the organisation unit's Location instance.
ORGANISATION_UNIT_VALUE_TYPE = "ORGANISATION_UNIT"

# The plain decimal and integer forms an FSH numeric literal may take. They are deliberately
# narrower than what `float()` and `int()` accept: FSH writes a numeric answer unquoted, so
# `NaN`, `Infinity`, and an exponent (`1e3`) are not numbers a FHIR primitive can carry, a
# leading `+` or a leading zero (`01.5`) is not the canonical lexical form, and `int()` would
# additionally read the underscores and surrounding whitespace of `1_0` as ten. A value that
# does not match is answered as a string rather than emitted as an invalid literal.
_FSH_DECIMAL_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
_FSH_INTEGER_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)$")

#: What an example declares when a response profile's 1..1 element (D2Period, authored) is missing.
_BASE_RESPONSE_RESOURCE = "QuestionnaireResponse"

#: The DHIS2 wire spellings of a true and a false boolean value.
_TRUE_LITERALS = frozenset({"true", "1"})
_FALSE_LITERALS = frozenset({"false", "0"})

#: The answer element everything unmapped - and everything that will not cast - falls back to.
DEFAULT_ANSWER_ELEMENT = "valueString"

#: How each form kind reads in the prose an example describes itself with.
_KIND_LABELS: dict[FormKind, str] = {
    "aggregate": "data set",
    "event": "event program",
    "tracker-event": "tracker program stage",
}

#: How many days back a synthetic event may have occurred.
_SYNTHETIC_EVENT_WINDOW_DAYS = 30

#: The character a DHIS2 UID opens on, and the characters its remaining ten places take.
_UID_LEADING_CHARACTERS = string.ascii_letters
_UID_TRAILING_CHARACTERS = string.ascii_letters + string.digits

#: How many places follow the leading letter of a DHIS2 UID.
_UID_TRAILING_LENGTH = 10

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


class _TrackerContextView(BaseModel):
    """The tracker context of one example: the enrollment, the tracked entity, and the unit it was captured at."""

    model_config = ConfigDict(frozen=True)

    enrollment_extension: str
    organisation_unit_extension: str
    organisation_unit_uid: str
    enrollment_uid: str | None = None
    tracked_entity_uid: str | None = None


class _Answer(BaseModel):
    """One typed FHIR answer as FSH writes it: the `value[x]` element it lands on and its rendered literal."""

    model_config = ConfigDict(frozen=True)

    element: str
    literal: str


class _ItemView(BaseModel):
    """One emitted response item, its FSH soft-index paths and its typed answers already rendered."""

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
    tracker: _TrackerContextView | None = None
    authored: str | None = None
    items: list[_ItemView] = Field(default_factory=list)


class ExampleTally(BaseModel):
    """Per-run tally of the example outcomes worth a note: skipped values and typing fall-backs.

    Both emitters tally into one of these and roll it up the same way, so an FSH run and a
    document run raise the identical notes about the identical responses.
    """

    unknown_data_elements: list[str] = Field(default_factory=list)
    untyped_values: list[str] = Field(default_factory=list)
    uncoded_options: list[str] = Field(default_factory=list)
    unpublished_organisation_units: list[str] = Field(default_factory=list)
    periodless_data_sets: list[str] = Field(default_factory=list)
    unauthored_responses: list[str] = Field(default_factory=list)
    incomplete_tracker_responses: list[str] = Field(default_factory=list)

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
        if self.unpublished_organisation_units:
            notes.append(
                aggregate_note(
                    f"{len(self.unpublished_organisation_units)} example answers reference an organisation "
                    "unit outside the org-unit selection, which the IG publishes no Location for; left "
                    "unanswered",
                    self.unpublished_organisation_units,
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
                    "instead of the event or tracker event response profile",
                    self.unauthored_responses,
                )
            )
        if self.incomplete_tracker_responses:
            notes.append(
                aggregate_note(
                    f"{len(self.incomplete_tracker_responses)} examples lack the enrollment or tracked entity "
                    "a tracker event carries; the base QuestionnaireResponse is declared instead of the tracker "
                    "event response profile",
                    self.incomplete_tracker_responses,
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
    published_organisation_unit_uids: frozenset[str] | None = None,
) -> FshBuild:
    """Build one `examples/<targetUid>-<n>.fsh` QuestionnaireResponse per example response.

    `option_set_plan` is the identity plan the terminology target emits from, so a coded answer
    names the CodeSystem the same run writes under either naming source. The concept codes come
    from `concept_assignments`, once per set, for the same reason: an answer names a concept the
    terminology target really wrote, fall-backs and all.

    `published_organisation_unit_uids` is the org-unit selection the registry target writes a
    Location for. Passing it lets an `ORGANISATION_UNIT` answer naming a unit outside that
    selection be left unanswered instead of referencing a Location the IG never publishes;
    leaving it None emits every such answer unchecked.
    """
    build = FshBuild()
    rules = ExampleAnswerRules(
        timezone=config.timezone, published_organisation_unit_uids=published_organisation_unit_uids
    )
    foundation = FoundationNaming.from_naming(config.naming)
    index = option_set_identity_index(option_set_plan, bound_option_set_uids(sources), config)
    sources_by_uid = {source.uid: source for source in sources}
    option_sets_by_uid = {option_set.uid: option_set for option_set in option_sets}
    assignments = example_concept_assignments(option_sets, config)
    template = _ENVIRONMENT.get_template("questionnaire-response.fsh.jinja")
    tally = ExampleTally()
    ordinals: dict[str, int] = {}
    for response in responses:
        source = sources_by_uid.get(response.target_uid)
        if source is None:
            continue
        ordinal = ordinals.get(response.target_uid, 0) + 1
        ordinals[response.target_uid] = ordinal
        view = _example_view(
            response, source, option_sets_by_uid, assignments, index.identities, foundation, canonical, tally, rules
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


def example_concept_assignments(
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
    """Generate one target's `n`-th example: its period or occurrence, its tracker context, then its answers."""
    generator = random.Random(_seed(source.uid, ordinal))  # noqa: S311 - illustrative values, not a secret
    period = _synthetic_period(source, today)
    window = _SyntheticWindow.of_period(period) if period is not None else _SyntheticWindow.recent(today)
    instance_id = f"{source.uid}-example-{ordinal}"
    authored: str | None = None
    if source.kind != "aggregate":
        authored = f"{window.pick_date(generator).isoformat()}T{_pick_hour(generator)}:00:00Z"
    tracked_entity_uid: str | None = None
    enrollment_uid: str | None = None
    if source.kind == "tracker-event":
        tracked_entity_uid = _synthetic_uid(generator)
        enrollment_uid = _synthetic_uid(generator)
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
        tracked_entity_uid=tracked_entity_uid,
        enrollment_uid=enrollment_uid,
        answers=answers,
    )


def _seed(target_uid: str, ordinal: int) -> int:
    """The RNG seed for one target's `n`-th example: the leading 64 bits of a SHA-256 digest."""
    digest = hashlib.sha256(f"{target_uid}:{ordinal}".encode()).digest()
    return int.from_bytes(digest[:_SEED_BYTES], "big")


def _synthetic_uid(generator: random.Random) -> str:
    """A seeded DHIS2-shaped UID: one ASCII letter followed by ten alphanumeric places."""
    leading = generator.choice(_UID_LEADING_CHARACTERS)
    trailing = "".join(generator.choice(_UID_TRAILING_CHARACTERS) for _ in range(_UID_TRAILING_LENGTH))
    return f"{leading}{trailing}"


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
    return MULTI_VALUE_SEPARATOR.join(generator.sample(stored, wanted))


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
    """Every question of one form in structure order, one entry per option combo where disaggregated.

    Disaggregation is the questionnaire emitter's own rule, so a response answers exactly the
    `linkId`s its form asks: an aggregate question splits into one key per category option combo,
    and an event or tracker-event question stays flat however its data element is categorised.
    """
    keys: list[_AnswerableKey] = []
    for item in source_items(source):
        if is_disaggregated(item, source.kind) and item.category_combo is not None:
            keys.extend(
                _AnswerableKey(item=item, category_option_combo_uid=option_combo.uid)
                for option_combo in item.category_combo.option_combos
            )
        else:
            keys.append(_AnswerableKey(item=item))
    return keys


def example_period(
    response: ExampleResponseIn, source: QuestionnaireSourceIn, tally: ExampleTally
) -> PeriodValue | None:
    """The reporting period an example carries, tallying a data set whose period could not be resolved."""
    if response.period is not None:
        return response.period
    if source.kind == "aggregate":
        tally.periodless_data_sets.append(f"{source.name} ({source.uid})")
    return None


def example_tracker_context(
    response: ExampleResponseIn, source: QuestionnaireSourceIn, tally: ExampleTally
) -> ExampleTrackerContext | None:
    """The tracker context a stage's response carries, tallied when the enrollment or tracked entity is missing."""
    if source.kind != "tracker-event":
        return None
    context = ExampleTrackerContext(
        organisation_unit_uid=response.organisation_unit_uid,
        enrollment_uid=response.enrollment_uid,
        tracked_entity_uid=response.tracked_entity_uid,
    )
    if not context.is_complete:
        tally.incomplete_tracker_responses.append(response.instance_id)
    return context


def example_is_complete(
    kind: FormKind,
    *,
    period: PeriodValue | None,
    authored: str | None,
    tracker: ExampleTrackerContext | None,
) -> bool:
    """Whether an example carries every 1..1 element its kind's response profile requires.

    An incomplete example claims no profile: FSH declares the base `QuestionnaireResponse`
    instead of the kind's profile, and a served document carries no `meta.profile`.
    """
    if kind == "aggregate":
        return period is not None
    if kind == "tracker-event":
        return authored is not None and tracker is not None and tracker.is_complete
    return authored is not None


def _example_view(
    response: ExampleResponseIn,
    source: QuestionnaireSourceIn,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    identities: dict[str, OptionSetIdentity],
    foundation: FoundationNaming,
    canonical: str,
    tally: ExampleTally,
    rules: ExampleAnswerRules,
) -> _ExampleView:
    """Project one example response onto the view the QuestionnaireResponse template renders."""
    label = _KIND_LABELS[source.kind]
    display_name = source_display_name(source)
    period = example_period(response, source, tally)
    answers = example_answers(response, source, option_sets_by_uid, assignments, tally, rules)
    authored = example_authored(response, tally, rules)
    tracker = example_tracker_context(response, source, tally)
    complete = example_is_complete(source.kind, period=period, authored=authored, tracker=tracker)
    return _ExampleView(
        instance_id=response.instance_id,
        instance_of=_response_profile(source.kind, foundation, complete=complete),
        questionnaire_url=f"{canonical}/Questionnaire/{source.uid}",
        title_literal=page_text(f"Example response - {display_name}"),
        description_literal=page_text(
            f"Example QuestionnaireResponse against the DHIS2 {label} {display_name} ({source.uid})."
        ),
        form_type_extension=foundation.form_type_extension,
        form_type_code=source.kind,
        organisation_unit_uid=response.organisation_unit_uid,
        status_code=response.status_code,
        period=_period_view(period, foundation),
        tracker=_tracker_view(tracker, foundation),
        authored=authored,
        items=_item_views(example_items(source, answers), identities, depth=0),
    )


def _period_view(period: PeriodValue | None, foundation: FoundationNaming) -> _PeriodExtensionView | None:
    """The D2Period extension one example's reporting period renders as."""
    if period is None:
        return None
    return _PeriodExtensionView(
        extension=foundation.period_extension,
        iso=period.iso,
        period_type=period.period_type,
        start_date=period.start_date,
        end_date=period.end_date,
    )


def _tracker_view(context: ExampleTrackerContext | None, foundation: FoundationNaming) -> _TrackerContextView | None:
    """The tracker extensions one stage response renders, under the run's foundation names."""
    if context is None:
        return None
    return _TrackerContextView(
        enrollment_extension=foundation.tracker_enrollment_extension,
        organisation_unit_extension=foundation.organisation_unit_extension,
        organisation_unit_uid=context.organisation_unit_uid,
        enrollment_uid=context.enrollment_uid,
        tracked_entity_uid=context.tracked_entity_uid,
    )


def _response_profile(kind: FormKind, foundation: FoundationNaming, *, complete: bool) -> str:
    """The declared instance type: the kind's response profile, or the base resource when a 1..1 element is missing."""
    if not complete:
        return _BASE_RESPONSE_RESOURCE
    if kind == "aggregate":
        return foundation.aggregate_response_profile
    if kind == "tracker-event":
        return foundation.tracker_event_response_profile
    return foundation.event_response_profile


def example_authored(response: ExampleResponseIn, tally: ExampleTally, rules: ExampleAnswerRules) -> str | None:
    """The response's authoring timestamp as an R4 dateTime, dropped and tallied when it is not one."""
    if response.authored is None:
        return None
    normalized = zoned_date_time(response.authored.strip(), rules.timezone)
    if is_fhir_date_time(normalized):
        return normalized
    tally.unauthored_responses.append(f"{response.instance_id} = {response.authored!r}")
    return None


def example_answers(
    response: ExampleResponseIn,
    source: QuestionnaireSourceIn,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    tally: ExampleTally,
    rules: ExampleAnswerRules,
) -> dict[str, list[ExampleAnswer]]:
    """Type every captured value and index it by the questionnaire `linkId` it answers.

    The `linkId` shaping is the questionnaire emitter's own disaggregation rule, so an aggregate
    value lands on `<deUid>.<cocUid>` and an event value lands on `<deUid>` whatever category
    combo its data element declares.
    """
    items_by_uid = {item.uid: item for item in source_items(source)}
    answers: dict[str, list[ExampleAnswer]] = {}
    for captured in response.answers:
        item = items_by_uid.get(captured.data_element_uid)
        if item is None:
            tally.unknown_data_elements.append(f"{captured.data_element_uid} in {response.instance_id}")
            continue
        link_id = captured.data_element_uid
        if is_disaggregated(item, source.kind) and captured.category_option_combo_uid is not None:
            link_id = f"{link_id}.{captured.category_option_combo_uid}"
        answers[link_id] = _typed_answers(item, captured.value, option_sets_by_uid, assignments, tally, rules)
    return answers


def _typed_answers(
    item: QuestionnaireItemIn,
    value: str,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    tally: ExampleTally,
    rules: ExampleAnswerRules,
) -> list[ExampleAnswer]:
    """Cast one captured value onto the FHIR answer type its value type asks for - several for MULTI_TEXT."""
    if item.option_set_uid is not None:
        selected = value.split(MULTI_VALUE_SEPARATOR) if item.value_type == MULTI_VALUE_TYPE else [value]
        coded = [
            _coded_answer(item, item.option_set_uid, part.strip(), option_sets_by_uid, assignments, tally)
            for part in selected
        ]
        return [answer for answer in coded if answer is not None]
    typed = _typed_answer(item, value, tally, rules)
    return [typed] if typed is not None else []


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


def _typed_answer(
    item: QuestionnaireItemIn, value: str, tally: ExampleTally, rules: ExampleAnswerRules
) -> ExampleAnswer | None:
    """Cast one DHIS2 value string onto the FHIR answer type its value type asks for; None when unanswerable."""
    text = value.strip()
    element = answer_element(item.value_type)
    if element == "valueInteger":
        return _integer_answer(item, text, tally)
    if element == "valueDecimal":
        return _decimal_answer(item, text, tally)
    if element == "valueBoolean":
        return _boolean_answer(item, text, tally)
    if element in _TEMPORAL_ELEMENTS:
        return _temporal_answer(item, text, element, tally, rules)
    if element == "valueUri":
        return ExampleAnswer(element=element, text_value=text)
    if element == "valueReference":
        return _location_answer(item, text, tally, rules)
    return ExampleAnswer(element=DEFAULT_ANSWER_ELEMENT, text_value=value)


def _location_answer(
    item: QuestionnaireItemIn, text: str, tally: ExampleTally, rules: ExampleAnswerRules
) -> ExampleAnswer | None:
    """Answer an organisation-unit question as a Location reference, when the IG publishes that Location.

    A unit outside the org-unit selection has no Location in the guide, so the answer would point
    at a resource no consumer can resolve. It is left unanswered and tallied instead, exactly as
    an option the CodeSystem holds no concept for is.
    """
    published = rules.published_organisation_unit_uids
    if published is not None and text not in published:
        tally.unpublished_organisation_units.append(f"{item.name} ({item.uid}) = {text}")
        return None
    return ExampleAnswer(element="valueReference", location_uid=text)


def _temporal_answer(
    item: QuestionnaireItemIn, text: str, element: str, tally: ExampleTally, rules: ExampleAnswerRules
) -> ExampleAnswer:
    """Answer a date / dateTime / time question, normalising DHIS2's spelling into the R4 primitive."""
    if element == "valueDate":
        normalized = text.partition("T")[0]
        valid = is_fhir_date(normalized)
    elif element == "valueDateTime":
        normalized = zoned_date_time(text, rules.timezone)
        valid = is_fhir_date_time(normalized)
    else:
        normalized = seconds_precision(text)
        valid = is_fhir_time(normalized)
    if not valid:
        return _fallback(item, text, tally)
    return ExampleAnswer(element=element, text_value=normalized)


def _integer_answer(item: QuestionnaireItemIn, text: str, tally: ExampleTally) -> ExampleAnswer:
    """Answer an integer question, falling back to a string when the stored value is not a plain integer."""
    if not _FSH_INTEGER_PATTERN.match(text):
        return _fallback(item, text, tally)
    return ExampleAnswer(element="valueInteger", integer_value=int(text))


def _decimal_answer(item: QuestionnaireItemIn, text: str, tally: ExampleTally) -> ExampleAnswer:
    """Answer a decimal question, keeping the stored precision but refusing what is not a plain decimal."""
    if not _FSH_DECIMAL_PATTERN.match(text):
        return _fallback(item, text, tally)
    return ExampleAnswer(element="valueDecimal", decimal_value=text)


def _boolean_answer(item: QuestionnaireItemIn, text: str, tally: ExampleTally) -> ExampleAnswer:
    """Answer a boolean question from DHIS2's `true`/`false` (or `1`/`0`) spellings."""
    lowered = text.lower()
    if lowered in _TRUE_LITERALS:
        return ExampleAnswer(element="valueBoolean", boolean_value=True)
    if lowered in _FALSE_LITERALS:
        return ExampleAnswer(element="valueBoolean", boolean_value=False)
    return _fallback(item, text, tally)


def _coded_answer(
    item: QuestionnaireItemIn,
    option_set_uid: str,
    value: str,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    tally: ExampleTally,
) -> ExampleAnswer | None:
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
    coding = ExampleCoding(option_set_uid=option_set_uid, concept_code=concept_code, display=option.name)
    return ExampleAnswer(element="valueCoding", coding=coding)


def _option_for(option_set: OptionSetIn, value: str) -> OptionIn | None:
    """Resolve a stored DHIS2 value to its option - by code, which is what a data value holds, then by UID."""
    by_code = next((option for option in option_set.options if option.code == value), None)
    if by_code is not None:
        return by_code
    return next((option for option in option_set.options if option.uid == value), None)


def _fallback(item: QuestionnaireItemIn, value: str, tally: ExampleTally) -> ExampleAnswer:
    """Answer as a plain string and tally why, so a run says how much it could not type."""
    tally.untyped_values.append(f"{item.name} ({item.uid}) = {value!r}")
    return ExampleAnswer(element=DEFAULT_ANSWER_ELEMENT, text_value=value)


def example_items(source: QuestionnaireSourceIn, answers: dict[str, list[ExampleAnswer]]) -> list[ExampleItem]:
    """Mirror the questionnaire's item tree, keeping only the branches an answer reaches."""
    items: list[ExampleItem] = []
    for section in source.sections:
        nested = [nested_item for item in section.items for nested_item in _data_element_items(item, source, answers)]
        if not nested:
            continue
        items.append(ExampleItem(link_id=section.uid, items=nested))
    for item in source.flat_items:
        items.extend(_data_element_items(item, source, answers))
    return items


def _data_element_items(
    item: QuestionnaireItemIn, source: QuestionnaireSourceIn, answers: dict[str, list[ExampleAnswer]]
) -> list[ExampleItem]:
    """Build one data element's response items: an answered question, or a group of option combos."""
    if is_disaggregated(item, source.kind) and item.category_combo is not None:
        cells = [
            ExampleItem(link_id=f"{item.uid}.{option_combo.uid}", answers=answers[f"{item.uid}.{option_combo.uid}"])
            for option_combo in item.category_combo.option_combos
            if f"{item.uid}.{option_combo.uid}" in answers
        ]
        if cells:
            return [ExampleItem(link_id=item.uid, items=cells)]
    answered = answers.get(item.uid)
    return [ExampleItem(link_id=item.uid, answers=answered)] if answered else []


def _item_views(items: list[ExampleItem], identities: dict[str, OptionSetIdentity], *, depth: int) -> list[_ItemView]:
    """Flatten the shared item tree onto the FSH soft-index paths, rendering each answer's literal."""
    views: list[_ItemView] = []
    for item in items:
        views.append(
            _ItemView(
                new_path=_new_path(depth),
                path=_set_path(depth),
                link_id=item.link_id,
                answers=[_fsh_answer(answer, identities) for answer in item.answers],
            )
        )
        views.extend(_item_views(item.items, identities, depth=depth + 1))
    return views


def _fsh_answer(answer: ExampleAnswer, identities: dict[str, OptionSetIdentity]) -> _Answer:
    """Render one typed answer as the FSH literal its `value[x]` element takes."""
    return _Answer(element=answer.element, literal=_fsh_literal(answer, identities))


def _fsh_literal(answer: ExampleAnswer, identities: dict[str, OptionSetIdentity]) -> str:
    """The FSH literal one typed answer writes - a bare number, a quoted string, or a coding call."""
    if answer.element == "valueInteger":
        return str(answer.integer_value)
    if answer.element == "valueDecimal":
        return str(answer.decimal_value)
    if answer.element == "valueBoolean":
        return "true" if answer.boolean_value else "false"
    if answer.element == "valueReference":
        return f"Reference(Location/{answer.location_uid})"
    if answer.element == "valueCoding" and answer.coding is not None:
        system = identities[answer.coding.option_set_uid].code_system_name
        return f"{system}{fsh_code(answer.coding.concept_code)} {quote(answer.coding.display)}"
    return quote(answer.text_value or "")


def _new_path(depth: int) -> str:
    """The FSH path that opens a new item at `depth` (e.g. `item[=].item[+]`)."""
    return f"{'item[=].' * depth}item[+]"


def _set_path(depth: int) -> str:
    """The FSH path that addresses the item just opened at `depth` (e.g. `item[=].item[=]`)."""
    return f"{'item[=].' * depth}item[=]"
