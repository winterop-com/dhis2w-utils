"""Example schemas: the `[generate.examples]` selection plus the emitter projections."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.period.schemas import PeriodValue
from dhis2w_fhir.resources.questionnaires.schemas import FormKind

#: Where an example response's answers come from: generated locally, or read off the instance.
ExampleSource = Literal["synthetic", "instance"]

#: The most examples one questionnaire target may carry - past a handful they stop illustrating.
MAXIMUM_EXAMPLES_PER_TARGET = 10


class ExampleSelection(BaseModel):
    """How many example responses each questionnaire target gets, and where their values come from.

    The `[generate.examples]` table of `fhir.toml`. `per_target = 0` disables the target
    entirely. `source` defaults to `synthetic` because an example is published: real values
    off a production instance would travel into the IG, so reading them is opt-in.
    """

    model_config = ConfigDict(extra="forbid")

    per_target: int = Field(default=1, ge=0, le=MAXIMUM_EXAMPLES_PER_TARGET)
    source: ExampleSource = "synthetic"


class ExampleAnswerRules(BaseModel):
    """What a captured value is read against: the zone behind its clock, and the units the IG publishes.

    `timezone` is the `[generate] timezone` IANA zone DHIS2's zone-less timestamps are wall-clock
    readings in (BUGS.md #62); None reads them as UTC. `published_organisation_unit_uids` is the
    org-unit selection the registry target writes a Location for, so an `ORGANISATION_UNIT` answer
    naming a unit outside it is left unanswered rather than pointed at a Location nobody wrote;
    None means this build does not know the selection and every such answer is emitted unchecked.
    """

    model_config = ConfigDict(frozen=True)

    timezone: str | None = None
    published_organisation_unit_uids: frozenset[str] | None = None


class SyntheticPlacement(BaseModel):
    """The organisation units one questionnaire target's synthetic responses may be captured at.

    DHIS2 scopes every data set and program to the organisation units it is assigned to, and a
    write against a unit outside that assignment is refused (`E1029`). The load-set path fills
    this with the intersection of the published registry selection and the target's own DHIS2
    assignment, sorted, so a generated response names a unit the target really reports for and
    the guide really publishes a Location for. An empty intersection is not representable: the
    target is dropped with a note before generation rather than pointed at a unit DHIS2 refuses.
    """

    model_config = ConfigDict(frozen=True)

    organisation_unit_uids: tuple[str, ...] = Field(min_length=1)


class RegistrationIdentities(BaseModel):
    """The two DHIS2 identities one registration response mints: the person, and the enrollment it creates.

    A corpus is internally consistent only when the stage responses of a tracker program answer
    against an enrollment something in the same corpus creates, so the pair is derived from the
    program UID and the registration's ordinal and read twice - once by the registration that mints
    it, once by every stage response assigned to it.
    """

    model_config = ConfigDict(frozen=True)

    tracked_entity_uid: str
    enrollment_uid: str


class ExampleAnswerIn(BaseModel):
    """One captured value, keyed the way DHIS2 keys it: data element plus category option combo.

    `value` is the DHIS2 wire string whatever the data element's value type is - the emitter
    casts it to the FHIR answer type, so the projection stays the shape both sources produce.
    """

    model_config = ConfigDict(frozen=True)

    data_element_uid: str
    category_option_combo_uid: str | None = None
    value: str


class ExampleResponseIn(BaseModel):
    """One example response: which form it answers, the context it was captured in, and its values.

    `tracked_entity_uid` and `enrollment_uid` are carried by both tracker kinds: a tracker event
    belongs to one enrollment of one tracked entity, and a registration response creates that
    pair. Both UIDs travel onto the response as the subject identifier and the enrollment
    extension either way - what differs is who authored them, which the response profiles say.

    `enrolled_at` and `incident_at` are carried by a registration response alone: they are the
    two dates the enrollment it creates holds, and only the form that creates one states them.

    `attribute_option_combo_uid` is the third key of an aggregate response - a data value set is
    keyed by `(orgUnit, period, attributeOptionCombo)`. It rides onto the response as the
    `D2AttributeOptionCombo` extension when the form publishes a vocabulary to code it from, and
    is otherwise the default combo, which the guide says by publishing nothing.
    """

    model_config = ConfigDict(frozen=True)

    instance_id: str
    target_uid: str
    kind: FormKind
    organisation_unit_uid: str
    status_code: str
    period: PeriodValue | None = None
    attribute_option_combo_uid: str | None = None
    authored: str | None = None
    tracked_entity_uid: str | None = None
    enrollment_uid: str | None = None
    enrolled_at: str | None = None
    incident_at: str | None = None
    answers: list[ExampleAnswerIn] = Field(default_factory=list)


class ExampleCoding(BaseModel):
    """The concept one option-set answer selects: the set it is drawn from, its concept code, its display.

    The option set is named by UID rather than by system, because the two emitters name the same
    CodeSystem differently: FSH writes the `D2OS_..._CS` alias SUSHI resolves, and the document
    path writes the canonical URL the run publishes it at.
    """

    model_config = ConfigDict(frozen=True)

    option_set_uid: str
    concept_code: str
    display: str


class ExampleAttributeOptionCombo(BaseModel):
    """The attribute option combo one aggregate response is keyed under, as the coding it is written as.

    The combo is named by the attribute category combo's UID rather than by system, for the same
    reason a coded answer names its option set by UID: the two emitters spell the CodeSystem
    differently - FSH writes the `D2AOC_..._CS` name SUSHI resolves, the document path writes the
    canonical URL the run publishes it at - and both resolve it through the one identity plan.
    """

    model_config = ConfigDict(frozen=True)

    combo_uid: str
    concept_code: str
    display: str


class ExampleAnswer(BaseModel):
    """One typed FHIR answer: the `value[x]` element it lands on, and the value cast to that element's type.

    `element` decides which carrier holds the value: `decimal_value` keeps the lexical decimal so
    the stored precision survives, `location_uid` is the organisation unit a `valueReference`
    points a Location at, and everything textual - string, uri, date, dateTime, time - lands on
    `text_value`.
    """

    model_config = ConfigDict(frozen=True)

    element: str
    text_value: str | None = None
    integer_value: int | None = None
    decimal_value: str | None = None
    boolean_value: bool | None = None
    location_uid: str | None = None
    coding: ExampleCoding | None = None


class ExampleItem(BaseModel):
    """One response item: an answered question, or a group nesting the section or disaggregation below it."""

    model_config = ConfigDict(frozen=True)

    link_id: str
    answers: list[ExampleAnswer] = Field(default_factory=list)
    items: list[ExampleItem] = Field(default_factory=list)


class ExampleTrackerContext(BaseModel):
    """The tracker context one tracker response carries: the enrollment, the tracked entity, the capture unit.

    A registration response fills the same three and adds the enrollment's dates, because it is
    the response that creates the enrollment the stage responses are captured against.
    """

    model_config = ConfigDict(frozen=True)

    organisation_unit_uid: str
    enrollment_uid: str | None = None
    tracked_entity_uid: str | None = None
    enrolled_at: str | None = None
    incident_at: str | None = None

    @property
    def is_complete(self) -> bool:
        """Whether both the enrollment and the tracked entity a tracker event always carries are present."""
        return self.enrollment_uid is not None and self.tracked_entity_uid is not None

    @property
    def is_registration_complete(self) -> bool:
        """Whether the pair a registration mints is present and dated, which its profile requires 1..1."""
        return self.is_complete and self.enrolled_at is not None

    @property
    def is_entity_complete(self) -> bool:
        """Whether the person a person-only registration mints is present, which is all its profile requires."""
        return self.tracked_entity_uid is not None
