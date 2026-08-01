"""Questionnaire schemas: the target selection, the emitter projections, and the derived FSH names."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.names import join_id_tokens

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

#: The form kinds a Questionnaire is generated from, and the D2FormType code each carries.
FormKind = Literal["aggregate", "event"]


class TargetSelection(BaseModel):
    """Which DHIS2 objects a data-definition target covers - `[generate.data_sets]` / `[generate.event_programs]`.

    UIDs only: names are not unique in DHIS2. An empty (or absent) list means none - a data
    definition is explicit opt-in, unlike the terminology targets where empty means all.
    """

    include_ids: list[str] = Field(default_factory=list)


class CategoryOptionComboIn(BaseModel):
    """One category option combo of a data element's disaggregation."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None


class CategoryComboIn(BaseModel):
    """The category combo a data element is disaggregated by, its option combos included."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    is_default: bool = False
    option_combos: list[CategoryOptionComboIn] = Field(default_factory=list)


class QuestionnaireItemIn(BaseModel):
    """One data element as a question: its value type, its option set, and its disaggregation."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    form_name: str | None = None
    value_type: str
    option_set_uid: str | None = None
    compulsory: bool = False
    category_combo: CategoryComboIn | None = None


class QuestionnaireSectionIn(BaseModel):
    """One section of a data-entry form, holding the data elements it groups."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    items: list[QuestionnaireItemIn] = Field(default_factory=list)


class QuestionnaireSourceIn(BaseModel):
    """One DHIS2 data set or event program as the Questionnaire projection the emitter consumes.

    `sections` carries the form when it has them and `flat_items` carries the rest, so a
    sectioned form fills the first, an unsectioned form the second, and a form that mixes
    the two fills both (the service notes that). Both empty is a degenerate form with no
    data elements.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    kind: FormKind
    sections: list[QuestionnaireSectionIn] = Field(default_factory=list)
    flat_items: list[QuestionnaireItemIn] = Field(default_factory=list)


class QuestionnaireNaming(BaseModel):
    """Derived FSH names and ids for questionnaire artifacts under the configurable naming tokens.

    Holds the four tokens it needs rather than the whole `[generate.naming]` table, so the
    emitter stays a leaf of the config document instead of a dependency of it. The data-element
    and category-option-combo support terminology takes the registry's fixed `DE` / `COC`
    tokens under the same prefix; `option_set` is here because an answer-bound item points at
    the option-set ValueSet the terminology target emits.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str
    data_set: str
    program: str
    option_set: str

    @classmethod
    def from_naming(cls, naming: NamingConfig) -> QuestionnaireNaming:
        """Project the `[generate.naming]` table onto the tokens questionnaire artifacts use."""
        return cls(
            prefix=naming.prefix,
            data_set=naming.data_set,
            program=naming.program,
            option_set=naming.option_set,
        )

    def source_token(self, kind: FormKind) -> str:
        """The naming token one form kind composes its name from (`DS` for a data set, `PR` for a program)."""
        return self.data_set if kind == "aggregate" else self.program

    def questionnaire_name(self, kind: FormKind, uid: str) -> str:
        """Computational `Questionnaire.name` for one source (e.g. `D2DSBfMAe6Itzgt`, `D2PRVBqh0ynB2wv`)."""
        return f"{self.prefix}{self.source_token(kind)}{uid}"

    @property
    def data_element_code_system(self) -> str:
        """FSH name of the data-element support CodeSystem (e.g. `D2DECS`)."""
        return f"{self.prefix}DECS"

    @property
    def data_element_code_system_id(self) -> str:
        """FHIR id of the data-element support CodeSystem (e.g. `d2-de-cs`)."""
        return join_id_tokens(self.prefix, "de", "cs")

    @property
    def data_element_value_set(self) -> str:
        """FSH name of the data-element support ValueSet (e.g. `D2DEVS`)."""
        return f"{self.prefix}DEVS"

    @property
    def data_element_value_set_id(self) -> str:
        """FHIR id of the data-element support ValueSet (e.g. `d2-de-vs`)."""
        return join_id_tokens(self.prefix, "de", "vs")

    @property
    def category_option_combo_code_system(self) -> str:
        """FSH name of the category-option-combo support CodeSystem (e.g. `D2COCCS`)."""
        return f"{self.prefix}COCCS"

    @property
    def category_option_combo_code_system_id(self) -> str:
        """FHIR id of the category-option-combo support CodeSystem (e.g. `d2-coc-cs`)."""
        return join_id_tokens(self.prefix, "coc", "cs")

    @property
    def category_option_combo_value_set(self) -> str:
        """FSH name of the category-option-combo support ValueSet (e.g. `D2COCVS`)."""
        return f"{self.prefix}COCVS"

    @property
    def category_option_combo_value_set_id(self) -> str:
        """FHIR id of the category-option-combo support ValueSet (e.g. `d2-coc-vs`)."""
        return join_id_tokens(self.prefix, "coc", "vs")

    def option_set_value_set(self, option_set_uid: str) -> str:
        """FSH name of the option-set ValueSet an answer-bound item points at (id-sourced naming)."""
        return f"{self.prefix}{self.option_set}{option_set_uid}VS"
