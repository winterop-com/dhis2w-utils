"""FSH emission for DHIS2 data sets and event programs: one Questionnaire instance per target.

A data set or an event program IS a data-capture form, so it maps onto a
`Questionnaire`: sections become `#group` items, data elements become
questions typed from their DHIS2 `valueType`, option-set-bound elements
become `#choice` items answered from the option-set ValueSet, and a data
element disaggregated by a non-default category combo becomes a group with
one child question per category option combo.

Every instance is `Usage: #definition` with the bare UID as its `id`, carries
both DHIS2 identifiers, and states which kind of DHIS2 form it came from
twice: through the `D2FormType` extension and as `Questionnaire.code`.

The output splits by what it describes: `data-sets/<uid>.fsh`,
`event-programs/<uid>.fsh`, and `data-dictionary/` for the two support
CodeSystem/ValueSet pairs both form kinds share - one over every data element
they reference, one over every category option combo. The support pairs live
under this target's own directories, so the option-set terminology target's
cleanup can never delete them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.names import code_or_uid, quote
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
)
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "DATA_DICTIONARY_DIRECTORY",
    "DATA_SET_DIRECTORY",
    "EVENT_PROGRAM_DIRECTORY",
    "ITEM_CONTROL_CODE_SYSTEM_URL",
    "ITEM_CONTROL_EXTENSION_URL",
    "QUESTIONNAIRE_DIRECTORIES",
    "build_questionnaire_artifacts",
]

#: Sync directory holding one Questionnaire per DHIS2 data set.
DATA_SET_DIRECTORY = "data-sets"

#: Sync directory holding one Questionnaire per DHIS2 event program.
EVENT_PROGRAM_DIRECTORY = "event-programs"

#: Sync directory holding the support terminology both form kinds share.
DATA_DICTIONARY_DIRECTORY = "data-dictionary"

#: The three sync directories the questionnaire target owns, in report order.
QUESTIONNAIRE_DIRECTORIES = (DATA_SET_DIRECTORY, EVENT_PROGRAM_DIRECTORY, DATA_DICTIONARY_DIRECTORY)

#: The standard R4 extension declaring how a Questionnaire item is rendered.
ITEM_CONTROL_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"

#: The CodeSystem the item-control extension's CodeableConcept is coded from (`#gtable` here).
ITEM_CONTROL_CODE_SYSTEM_URL = "http://hl7.org/fhir/questionnaire-item-control"

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.questionnaires", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

#: The FHIR `Questionnaire.item.type` each DHIS2 value type answers as; anything absent is a string.
_ITEM_TYPES_BY_VALUE_TYPE = {
    "TEXT": "string",
    "LONG_TEXT": "text",
    "NUMBER": "decimal",
    "INTEGER": "integer",
    "INTEGER_POSITIVE": "integer",
    "INTEGER_NEGATIVE": "integer",
    "INTEGER_ZERO_OR_POSITIVE": "integer",
    "BOOLEAN": "boolean",
    "TRUE_ONLY": "boolean",
    "DATE": "date",
    "DATETIME": "dateTime",
    "TIME": "time",
    "PERCENTAGE": "decimal",
    "UNIT_INTERVAL": "decimal",
    "ORGANISATION_UNIT": "reference",
}

_DEFAULT_ITEM_TYPE = "string"


class _FormKindProfile(BaseModel):
    """What one form kind contributes to its Questionnaire: identifier systems and prose label."""

    model_config = ConfigDict(frozen=True)

    identifier_system: str
    identifier_code_system: str
    label: str


#: The DHIS2 identifier systems and prose label each form kind carries.
_PROFILES_BY_KIND = {
    "aggregate": _FormKindProfile(
        identifier_system="$DHIS2-DS", identifier_code_system="$DHIS2-DS-CODE", label="data set"
    ),
    "event": _FormKindProfile(
        identifier_system="$DHIS2-PROGRAM", identifier_code_system="$DHIS2-PROGRAM-CODE", label="event program"
    ),
}


class _ItemView(BaseModel):
    """One emitted Questionnaire item, its FSH soft-index paths already resolved."""

    model_config = ConfigDict(frozen=True)

    new_path: str
    path: str
    link_id: str
    text_literal: str
    type_code: str
    code_token: str | None = None
    answer_value_set: str | None = None
    required: bool = False
    item_control: bool = False


class _QuestionnaireView(BaseModel):
    """Everything the Questionnaire template needs for one source, every conditional resolved."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    url: str
    title_literal: str
    title_element_literal: str
    description_literal: str
    identifier_system: str
    identifier_code_system: str
    identifier_code_literal: str
    form_type_extension: str
    form_type_code_system: str
    form_type_code: str
    ig_status: IgStatus
    items: list[_ItemView] = Field(default_factory=list)

    @property
    def experimental(self) -> bool:
        """Whether the Questionnaire is experimental - derived from the IG status."""
        return experimental_for_status(self.ig_status)


class _SupportConcept(BaseModel):
    """One data element or category option combo as a concept of a support CodeSystem."""

    model_config = ConfigDict(frozen=True)

    uid: str
    display_literal: str
    code_literal: str


class _SupportTerminologyView(BaseModel):
    """A support CodeSystem/ValueSet pair over the objects the generated questionnaires reference."""

    model_config = ConfigDict(frozen=True)

    code_system: str
    code_system_id: str
    value_set: str
    value_set_id: str
    title_literal: str
    description_literal: str
    property_base: str
    property_description_literal: str
    ig_status: IgStatus
    concepts: list[_SupportConcept] = Field(default_factory=list)

    @property
    def experimental(self) -> bool:
        """Whether the support pair is experimental - derived from the IG status."""
        return experimental_for_status(self.ig_status)


def build_questionnaire_artifacts(
    sources: list[QuestionnaireSourceIn], config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> FshBuild:
    """Build one `data-sets/` or `event-programs/` file per target plus the `data-dictionary/` support pairs."""
    build = FshBuild()
    names = QuestionnaireNaming.from_naming(config.naming)
    foundation = FoundationNaming.from_naming(config.naming)
    data_elements: dict[str, QuestionnaireItemIn] = {}
    option_combos: dict[str, CategoryOptionComboIn] = {}
    template = _ENVIRONMENT.get_template("questionnaire.fsh.jinja")
    for source in sorted(sources, key=lambda item: (item.name, item.uid)):
        _collect_referenced_objects(source, data_elements, option_combos)
        view = _questionnaire_view(source, names, foundation, canonical, ig_status=ig_status)
        build.artifacts.append(
            FshArtifact(
                relative_path=f"{_source_directory(source)}/{source.uid}.fsh",
                kind="instances",
                fsh_name=f"Questionnaire-{source.uid}",
                content=template.render(
                    questionnaire=view,
                    item_control_extension_url=ITEM_CONTROL_EXTENSION_URL,
                    item_control_code_system_url=ITEM_CONTROL_CODE_SYSTEM_URL,
                ),
            )
        )
    if data_elements:
        build.artifacts.append(_data_element_terminology(data_elements, names, config, ig_status=ig_status))
    if option_combos:
        build.artifacts.append(_option_combo_terminology(option_combos, names, config, ig_status=ig_status))
    return build


def _source_directory(source: QuestionnaireSourceIn) -> str:
    """The sync directory one form kind is written to."""
    return DATA_SET_DIRECTORY if source.kind == "aggregate" else EVENT_PROGRAM_DIRECTORY


def _questionnaire_view(
    source: QuestionnaireSourceIn,
    names: QuestionnaireNaming,
    foundation: FoundationNaming,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> _QuestionnaireView:
    """Project one source onto the view the Questionnaire template renders."""
    profile = _PROFILES_BY_KIND[source.kind]
    return _QuestionnaireView(
        uid=source.uid,
        name=names.questionnaire_name(source.kind, source.uid),
        url=f"{canonical}/Questionnaire/{source.uid}",
        title_literal=quote(f"Questionnaire - {source.name}"),
        title_element_literal=quote(source.name),
        description_literal=quote(f"DHIS2 {profile.label} {source.name} ({source.uid}) as a data capture form."),
        identifier_system=profile.identifier_system,
        identifier_code_system=profile.identifier_code_system,
        identifier_code_literal=quote(code_or_uid(source.code, source.uid)),
        form_type_extension=foundation.form_type_extension,
        form_type_code_system=foundation.form_type_code_system,
        form_type_code=source.kind,
        ig_status=ig_status,
        items=_item_views(source, names),
    )


def _item_views(source: QuestionnaireSourceIn, names: QuestionnaireNaming) -> list[_ItemView]:
    """Flatten the source's sections and unsectioned items into depth-first FSH item lines."""
    views: list[_ItemView] = []
    for section in source.sections:
        views.append(
            _ItemView(
                new_path=_new_path(0),
                path=_set_path(0),
                link_id=section.uid,
                text_literal=quote(section.name),
                type_code="group",
                item_control=any(_is_disaggregated(item) for item in section.items),
            )
        )
        for item in section.items:
            views.extend(_data_element_views(item, names, depth=1))
    for item in source.flat_items:
        views.extend(_data_element_views(item, names, depth=0))
    return views


def _data_element_views(item: QuestionnaireItemIn, names: QuestionnaireNaming, depth: int) -> list[_ItemView]:
    """Build one data element's item lines: a question, or a group with one child per option combo."""
    code_token = f"{names.data_element_code_system}#{item.uid} {quote(item.name)}"
    text_literal = quote(item.form_name or item.name)
    if not _is_disaggregated(item):
        return [
            _ItemView(
                new_path=_new_path(depth),
                path=_set_path(depth),
                link_id=item.uid,
                code_token=code_token,
                text_literal=text_literal,
                type_code=_item_type(item),
                answer_value_set=_answer_value_set(item, names),
                required=item.compulsory,
            )
        ]
    views = [
        _ItemView(
            new_path=_new_path(depth),
            path=_set_path(depth),
            link_id=item.uid,
            code_token=code_token,
            text_literal=text_literal,
            type_code="group",
            required=item.compulsory,
        )
    ]
    category_combo = item.category_combo
    option_combos = category_combo.option_combos if category_combo is not None else []
    for option_combo in option_combos:
        views.append(
            _ItemView(
                new_path=_new_path(depth + 1),
                path=_set_path(depth + 1),
                link_id=f"{item.uid}.{option_combo.uid}",
                code_token=f"{names.category_option_combo_code_system}#{option_combo.uid} {quote(option_combo.name)}",
                text_literal=quote(option_combo.name),
                type_code=_value_type_item_type(item.value_type),
            )
        )
    return views


def _is_disaggregated(item: QuestionnaireItemIn) -> bool:
    """Check whether a data element carries a real (non-default) category combo."""
    return item.category_combo is not None and not item.category_combo.is_default


def _item_type(item: QuestionnaireItemIn) -> str:
    """The item type one question answers as: `choice` when option-set bound, else its value type's."""
    if item.option_set_uid is not None:
        return "choice"
    return _value_type_item_type(item.value_type)


def _value_type_item_type(value_type: str) -> str:
    """Map a DHIS2 value type onto the FHIR item type it answers as, defaulting to a string."""
    return _ITEM_TYPES_BY_VALUE_TYPE.get(value_type, _DEFAULT_ITEM_TYPE)


def _answer_value_set(item: QuestionnaireItemIn, names: QuestionnaireNaming) -> str | None:
    """The option-set ValueSet an option-set-bound question is answered from."""
    if item.option_set_uid is None:
        return None
    return names.option_set_value_set(item.option_set_uid)


def _new_path(depth: int) -> str:
    """The FSH path that opens a new item at `depth` (e.g. `item[=].item[+]`)."""
    return f"{'item[=].' * depth}item[+]"


def _set_path(depth: int) -> str:
    """The FSH path that addresses the item just opened at `depth` (e.g. `item[=].item[=]`)."""
    return f"{'item[=].' * depth}item[=]"


def _collect_referenced_objects(
    source: QuestionnaireSourceIn,
    data_elements: dict[str, QuestionnaireItemIn],
    option_combos: dict[str, CategoryOptionComboIn],
) -> None:
    """Record every data element and category option combo one source's items reference."""
    items = [item for section in source.sections for item in section.items] + list(source.flat_items)
    for item in items:
        data_elements.setdefault(item.uid, item)
        if not _is_disaggregated(item) or item.category_combo is None:
            continue
        for option_combo in item.category_combo.option_combos:
            option_combos.setdefault(option_combo.uid, option_combo)


def _data_element_terminology(
    data_elements: dict[str, QuestionnaireItemIn],
    names: QuestionnaireNaming,
    config: GenerateConfig,
    *,
    ig_status: IgStatus,
) -> FshArtifact:
    """Build `data-dictionary/data-elements.fsh` over every data element the questionnaires reference."""
    concepts = [
        _SupportConcept(
            uid=item.uid,
            display_literal=quote(item.name),
            code_literal=quote(code_or_uid(None, item.uid)),
        )
        for item in sorted(data_elements.values(), key=lambda item: (item.name, item.uid))
    ]
    description = (
        "DHIS2 data elements captured by the generated questionnaires. Concept codes are DHIS2 data element UIDs."
    )
    view = _SupportTerminologyView(
        code_system=names.data_element_code_system,
        code_system_id=names.data_element_code_system_id,
        value_set=names.data_element_value_set,
        value_set_id=names.data_element_value_set_id,
        title_literal=quote("DHIS2 Data Elements"),
        description_literal=quote(description),
        property_base=f"{config.identifier_system_base}/property",
        property_description_literal=quote("DHIS2 data element code."),
        ig_status=ig_status,
        concepts=concepts,
    )
    return FshArtifact(
        relative_path=f"{DATA_DICTIONARY_DIRECTORY}/data-elements.fsh",
        kind="terminology-pair",
        fsh_name=names.data_element_code_system,
        content=_ENVIRONMENT.get_template("support-terminology.fsh.jinja").render(terminology=view),
    )


def _option_combo_terminology(
    option_combos: dict[str, CategoryOptionComboIn],
    names: QuestionnaireNaming,
    config: GenerateConfig,
    *,
    ig_status: IgStatus,
) -> FshArtifact:
    """Build `data-dictionary/category-option-combos.fsh` over every option combo the forms disaggregate by."""
    concepts = [
        _SupportConcept(
            uid=option_combo.uid,
            display_literal=quote(option_combo.name),
            code_literal=quote(code_or_uid(option_combo.code, option_combo.uid)),
        )
        for option_combo in sorted(option_combos.values(), key=lambda item: (item.name, item.uid))
    ]
    description = (
        "DHIS2 category option combos the generated questionnaires disaggregate by. "
        "Concept codes are DHIS2 category option combo UIDs."
    )
    view = _SupportTerminologyView(
        code_system=names.category_option_combo_code_system,
        code_system_id=names.category_option_combo_code_system_id,
        value_set=names.category_option_combo_value_set,
        value_set_id=names.category_option_combo_value_set_id,
        title_literal=quote("DHIS2 Category Option Combos"),
        description_literal=quote(description),
        property_base=f"{config.identifier_system_base}/property",
        property_description_literal=quote("DHIS2 category option combo code."),
        ig_status=ig_status,
        concepts=concepts,
    )
    return FshArtifact(
        relative_path=f"{DATA_DICTIONARY_DIRECTORY}/category-option-combos.fsh",
        kind="terminology-pair",
        fsh_name=names.category_option_combo_code_system,
        content=_ENVIRONMENT.get_template("support-terminology.fsh.jinja").render(terminology=view),
    )
