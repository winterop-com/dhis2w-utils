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

    per_target: int = Field(default=1, ge=0, le=MAXIMUM_EXAMPLES_PER_TARGET)
    source: ExampleSource = "synthetic"


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

    `tracked_entity_uid` and `enrollment_uid` are carried exactly by tracker-event responses:
    a tracker event belongs to one enrollment of one tracked entity, and both UIDs travel onto
    the response as the subject identifier and the enrollment extension.
    """

    model_config = ConfigDict(frozen=True)

    instance_id: str
    target_uid: str
    kind: FormKind
    organisation_unit_uid: str
    status_code: str
    period: PeriodValue | None = None
    authored: str | None = None
    tracked_entity_uid: str | None = None
    enrollment_uid: str | None = None
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
    """The tracker context one stage response carries: the enrollment, the tracked entity, the capture unit."""

    model_config = ConfigDict(frozen=True)

    organisation_unit_uid: str
    enrollment_uid: str | None = None
    tracked_entity_uid: str | None = None

    @property
    def is_complete(self) -> bool:
        """Whether both the enrollment and the tracked entity a tracker event always carries are present."""
        return self.enrollment_uid is not None and self.tracked_entity_uid is not None
