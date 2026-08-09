"""Attribute-combo schemas: the emitter projection, the artifact identities, and the per-form plan."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.notes import GenerateNote
from dhis2w_fhir.resources.option_sets.schemas import ConceptSourceIn


class AttributeComboIn(ConceptSourceIn):
    """One DHIS2 attribute category combo as the emitter projection, its attribute option combos included.

    A data set's own category combo is the third key of every value it holds - a data value set
    is keyed by `(orgUnit, period, attributeOptionCombo)` - and its category option combos are
    the values that key may take, which is the shape an option set and a category already have.
    So the combo lands on the shared concept-source projection and emits the same pair, built by
    the same concept-code assignment.
    """

    source_label: ClassVar[str] = "attribute category combo"
    member_label: ClassVar[str] = "attribute option combo"


class AttributeComboIdentity(BaseModel):
    """One attribute combo's emitted slug plus the FSH names and artifact ids derived from it.

    All three artifacts of one combo - the CodeSystem, the ValueSet a form's questionnaire binds
    by canonical, and the ConceptMap taking the concept codes back to DHIS2 - ride the one slug.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    slug: str
    fsh_name: str
    code_system_id: str
    value_set_id: str
    concept_map_id: str

    @property
    def code_system_name(self) -> str:
        """FSH name of the emitted CodeSystem (e.g. `D2AOC_Project_CS`)."""
        return f"{self.fsh_name}_CS"

    @property
    def value_set_name(self) -> str:
        """FSH name of the emitted ValueSet (e.g. `D2AOC_Project_VS`)."""
        return f"{self.fsh_name}_VS"

    @property
    def concept_map_name(self) -> str:
        """FSH name of the emitted ConceptMap (e.g. `D2AOC_Project_CM`)."""
        return f"{self.fsh_name}_CM"


class AttributeComboIdentityPlan(BaseModel):
    """Every attribute combo's identity in emission order, with the notes the slug assignment raised."""

    identities: list[AttributeComboIdentity] = Field(default_factory=list)
    notes: list[GenerateNote] = Field(default_factory=list)


class AttributeComboPlan(BaseModel):
    """Which attribute-option-combo vocabulary each form declares, keyed by the form's DHIS2 UID.

    A form absent from the plan publishes no vocabulary and its Questionnaire carries no
    `D2AttributeOptionCombos` extension - its data set rides the default category combo, so the
    default attribute option combo is the only key its values can take and absence says exactly
    that. Two data sets on one combo share one entry, because the plan is keyed by the form and
    valued by the combo's single identity.
    """

    model_config = ConfigDict(frozen=True)

    identities: dict[str, AttributeComboIdentity] = Field(default_factory=dict)
    """The published identity of every non-default attribute combo the run covers, by combo UID."""

    combo_uids: dict[str, str] = Field(default_factory=dict)
    """Which attribute combo each form rides, by form UID - the forms that declare one at all."""

    def identity_for(self, source_uid: str) -> AttributeComboIdentity | None:
        """The vocabulary one form declares, or None when it rides the default category combo."""
        combo_uid = self.combo_uids.get(source_uid)
        return None if combo_uid is None else self.identities.get(combo_uid)
