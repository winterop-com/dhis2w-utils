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
    """One example response: which form it answers, the context it was captured in, and its values."""

    model_config = ConfigDict(frozen=True)

    instance_id: str
    target_uid: str
    kind: FormKind
    organisation_unit_uid: str
    status_code: str
    period: PeriodValue | None = None
    authored: str | None = None
    answers: list[ExampleAnswerIn] = Field(default_factory=list)
