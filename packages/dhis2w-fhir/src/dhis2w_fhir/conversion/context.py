"""Assembling the translation context from the compiled IG artifacts a project publishes.

The translator reads one thing besides the response: a `ConversionContext`. This module builds it
from the very documents `d2w fhir serve` holds - the served Questionnaires, the option-set
CodeSystems, the ValueSets binding a question to its terminology, the ConceptMaps taking a
concept code back to its DHIS2 option code, and the published Locations whose ids are identity
stems rather than DHIS2 UIDs.

Two things the compiled IG deliberately does not publish are threaded in by the caller. The DHIS2
**value type** behind a question is one: a Questionnaire states an R4 item type, and `BOOLEAN` and
`TRUE_ONLY` share `#boolean`, so a caller holding the instance's metadata passes
`value_types_by_data_element` and the translator writes `TRUE_ONLY` values the way DHIS2 stores
them. Without it a boolean question is read as `BOOLEAN` and the response carries a note saying so.
The other is the project **timezone**, which is what a zoned R4 timestamp is read back through
(BUGS.md #62).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.conversion.schemas import (
    TARGET_KINDS_BY_FORM_KIND,
    CodedAnswerMode,
    ConversionContext,
    ConversionNaming,
    FormSpec,
    OptionEntry,
    OptionTable,
    QuestionSpec,
    WireValueKind,
)
from dhis2w_fhir.resources.questionnaires.schemas import FORM_KIND_PROFILES, FormKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_fhir.r4 import (
        CodeSystem,
        CodeSystemConcept,
        ConceptMap,
        Location,
        Questionnaire,
        QuestionnaireItem,
        ValueSet,
    )

__all__ = [
    "ANSWER_ELEMENTS_BY_ITEM_TYPE",
    "CELL_LINK_ID_SEPARATOR",
    "OPTION_CODE_PROPERTY",
    "OPTION_UID_PROPERTY",
    "ConversionContextError",
    "build_conversion_context",
    "build_form_spec",
    "build_option_table",
]

#: The separator a disaggregated cell's link id joins its data element and category option combo with.
CELL_LINK_ID_SEPARATOR = "."

#: The concept property carrying the DHIS2 option UID, written when concept codes are option codes.
OPTION_UID_PROPERTY = "dhis2-id"

#: The concept property carrying the DHIS2 option code, written when concept codes are option UIDs.
OPTION_CODE_PROPERTY = "dhis2-code"

#: The `value[x]` element a question answers on, keyed by the R4 item type the Questionnaire gives it.
#: The inverse of `ITEM_TYPES_BY_VALUE_TYPE`, which maps a DHIS2 value type onto an item type.
ANSWER_ELEMENTS_BY_ITEM_TYPE = {
    "boolean": "valueBoolean",
    "decimal": "valueDecimal",
    "integer": "valueInteger",
    "date": "valueDate",
    "dateTime": "valueDateTime",
    "time": "valueTime",
    "string": "valueString",
    "text": "valueString",
    "url": "valueUri",
    "attachment": "valueAttachment",
    "choice": "valueCoding",
    "open-choice": "valueCoding",
    "reference": "valueReference",
}

#: How each answerable R4 item type serialises onto the DHIS2 wire, before terminology and value type refine it.
_WIRE_KINDS_BY_ITEM_TYPE = {
    "boolean": WireValueKind.BOOLEAN,
    "decimal": WireValueKind.DECIMAL,
    "integer": WireValueKind.INTEGER,
    "date": WireValueKind.DATE,
    "dateTime": WireValueKind.DATE_TIME,
    "time": WireValueKind.TIME,
    "string": WireValueKind.TEXT,
    "text": WireValueKind.TEXT,
    "url": WireValueKind.URI,
    "attachment": WireValueKind.ATTACHMENT,
    "choice": WireValueKind.CODED,
    "open-choice": WireValueKind.CODED,
    "reference": WireValueKind.ORGANISATION_UNIT,
}

#: The item types that carry no answer of their own and only nest other items.
_STRUCTURAL_ITEM_TYPES = ("group", "display")

#: The DHIS2 value type whose data value is `"true"` or nothing at all - never `"false"`.
_TRUE_ONLY_VALUE_TYPE = "TRUE_ONLY"

#: The resource type a questionnaire canonical resolves to.
_QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"


class ConversionContextError(ValueError):
    """Raised when a compiled artifact cannot be read into the context the translator needs."""

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


def build_conversion_context(
    naming: ConversionNaming,
    questionnaires: Sequence[Questionnaire],
    *,
    code_systems: Sequence[CodeSystem] = (),
    value_sets: Sequence[ValueSet] = (),
    concept_maps: Sequence[ConceptMap] = (),
    locations: Sequence[Location] = (),
    value_types_by_data_element: dict[str, str] | None = None,
    coded_answer_mode: CodedAnswerMode = CodedAnswerMode.LENIENT,
    timezone: str | None = None,
) -> ConversionContext:
    """Read one project's compiled artifacts into the context every response is translated through.

    `questionnaires` decides which responses can be translated at all - a canonical absent here is
    a refusal, not a guess. `value_sets` binds a `#choice` question to the CodeSystem behind its
    `answerValueSet`, and `code_systems` (refined by `concept_maps` where a code-mode guide needs
    the DHIS2 option code back) is what a coded answer resolves against. `locations` is what turns
    a `Location/<id>` reference into the DHIS2 organisation unit UID it stands for, which under
    code-or-id naming is not the id itself.
    """
    code_system_urls = _code_system_urls_by_value_set(value_sets)
    tables = {
        table.system: table
        for table in (build_option_table(code_system, naming, concept_maps) for code_system in code_systems)
    }
    forms = {}
    for questionnaire in questionnaires:
        form = build_form_spec(questionnaire, naming, code_system_urls, value_types_by_data_element or {})
        forms[form.canonical] = form
    return ConversionContext(
        naming=naming,
        forms=forms,
        option_tables=tables,
        organisation_unit_uids_by_location_id=_organisation_unit_uids(locations, naming),
        coded_answer_mode=coded_answer_mode,
        timezone=timezone,
    )


def build_form_spec(
    questionnaire: Questionnaire,
    naming: ConversionNaming,
    code_system_urls_by_value_set: dict[str, str],
    value_types_by_data_element: dict[str, str],
) -> FormSpec:
    """Flatten one served Questionnaire into the form spec a response answering it translates through."""
    canonical = questionnaire.url
    if not canonical:
        raise ConversionContextError(f"the served {_QUESTIONNAIRE_RESOURCE_TYPE} carries no canonical url")
    form_kind = _form_kind(questionnaire, naming, canonical)
    questions: dict[str, QuestionSpec] = {}
    group_link_ids: set[str] = set()
    _walk(
        questionnaire.item or [],
        code_system_urls_by_value_set,
        value_types_by_data_element,
        questions,
        group_link_ids,
    )
    target_uid = _identifier_value(questionnaire, naming.target_identifier_system(form_kind))
    value_set = _attribute_option_combo_value_set(questionnaire, naming)
    return FormSpec(
        canonical=canonical,
        form_kind=form_kind,
        target_kind=TARGET_KINDS_BY_FORM_KIND[form_kind],
        data_set_uid=target_uid if form_kind == "aggregate" else None,
        program_uid=target_uid if form_kind == "event" else _identifier_value(questionnaire, naming.program_system),
        program_stage_uid=target_uid if form_kind == "tracker-event" else None,
        questions=questions,
        group_link_ids=frozenset(group_link_ids),
        attribute_option_combo_value_set=value_set,
        attribute_option_combo_system=code_system_urls_by_value_set.get(value_set or ""),
    )


def _attribute_option_combo_value_set(questionnaire: Questionnaire, naming: ConversionNaming) -> str | None:
    """The vocabulary one form declares its responses key their values from, or None on the default combo."""
    for extension in questionnaire.extension or []:
        if extension.url == naming.attribute_option_combos_url and extension.valueCanonical:
            return extension.valueCanonical
    return None


def build_option_table(
    code_system: CodeSystem,
    naming: ConversionNaming,
    concept_maps: Sequence[ConceptMap] = (),
) -> OptionTable:
    """Read one served CodeSystem into the option table a coded answer resolves against.

    The concept properties carry the complementary DHIS2 identifier both ways round, so the table
    is complete under `concept_code_source = "id"` from the CodeSystem alone. Under `"code"` an
    option whose DHIS2 code was not a usable concept code took the UID instead, and only the set's
    ConceptMap still knows the code - which is why the maps refine the table where they are given.
    """
    system = code_system.url
    if not system:
        raise ConversionContextError("a served CodeSystem carries no canonical url")
    read = (_option_entry(concept) for concept in code_system.concept or [])
    entries = [entry for entry in read if entry is not None]
    return OptionTable(system=system, entries=_mapped_entries(entries, system, naming, concept_maps))


def _option_entry(concept: CodeSystemConcept) -> OptionEntry | None:
    """Read one concept as the DHIS2 option it publishes, whichever spelling its code carries.

    A `dhis2-id` property means the concept code is the DHIS2 option code and the property is the
    UID - unless the two are equal, which is the code-mode fall-back and leaves the DHIS2 code
    unrecoverable from this document. Without that property the concept code is the UID and
    `dhis2-code` carries the option code, already fallen back to the UID where DHIS2 held none.
    """
    concept_code = concept.code
    if not concept_code:
        return None
    properties = {entry.code: entry for entry in concept.property or []}
    carried_uid = properties.get(OPTION_UID_PROPERTY)
    if carried_uid is not None:
        option_uid = carried_uid.valueCode or carried_uid.valueString or concept_code
        return OptionEntry(
            concept_code=concept_code,
            option_uid=option_uid,
            option_code=None if concept_code == option_uid else concept_code,
        )
    carried_code = properties.get(OPTION_CODE_PROPERTY)
    option_code = None if carried_code is None else (carried_code.valueString or carried_code.valueCode)
    return OptionEntry(concept_code=concept_code, option_uid=concept_code, option_code=option_code)


def _mapped_entries(
    entries: list[OptionEntry],
    system: str,
    naming: ConversionNaming,
    concept_maps: Sequence[ConceptMap],
) -> tuple[OptionEntry, ...]:
    """Refine one set's entries with the DHIS2 identifiers its ConceptMap carries, where a map was given.

    Two terminology families reach this table through one call - the option sets and the attribute
    option combos - and each names its own pair of DHIS2 target namespaces. A map only ever carries
    one family's targets, so reading both pairs resolves either without the caller saying which.
    """
    codes = _mapped_codes(system, (naming.option_code_system, naming.attribute_option_combo_code_system), concept_maps)
    uids = _mapped_codes(system, (naming.option_uid_system, naming.attribute_option_combo_uid_system), concept_maps)
    if not codes and not uids:
        return tuple(entries)
    return tuple(
        entry.model_copy(
            update={
                "option_code": codes.get(entry.concept_code, entry.option_code),
                "option_uid": uids.get(entry.concept_code, entry.option_uid),
            }
        )
        for entry in entries
    )


def _mapped_codes(system: str, target_systems: tuple[str, ...], concept_maps: Sequence[ConceptMap]) -> dict[str, str]:
    """Every `concept code -> DHIS2 identifier` row one system's maps carry onto any of the target namespaces."""
    mapped: dict[str, str] = {}
    for concept_map in concept_maps:
        for group in concept_map.group or []:
            if group.source != system or group.target not in target_systems:
                continue
            for element in group.element or []:
                code = element.code
                targets = element.target or []
                if code and targets and targets[0].code:
                    mapped[code] = targets[0].code or ""
    return mapped


def _code_system_urls_by_value_set(value_sets: Sequence[ValueSet]) -> dict[str, str]:
    """The CodeSystem behind every served ValueSet, which is what a question's `answerValueSet` resolves to."""
    urls: dict[str, str] = {}
    for value_set in value_sets:
        if not value_set.url:
            continue
        for include in (value_set.compose.include if value_set.compose else None) or []:
            if include.system:
                urls[value_set.url] = include.system
                break
    return urls


def _organisation_unit_uids(locations: Sequence[Location], naming: ConversionNaming) -> dict[str, str]:
    """The DHIS2 UID behind every published Location id, read off the identifier rather than assumed.

    Under `naming.source = "code"` a Location's id is the unit's code stem, so a `Location/<id>`
    reference resolves to a DHIS2 organisation unit only through the org-unit identifier slice.
    """
    uids: dict[str, str] = {}
    for location in locations:
        if not location.id:
            continue
        for identifier in location.identifier or []:
            if identifier.system == naming.organisation_unit_system and identifier.value:
                uids[location.id] = identifier.value
                break
    return uids


def _form_kind(questionnaire: Questionnaire, naming: ConversionNaming, canonical: str) -> FormKind:
    """The DHIS2 form kind the Questionnaire declares on its D2FormType extension."""
    declared = {
        extension.valueCode
        for extension in questionnaire.extension or []
        if extension.url == naming.form_type_url and extension.valueCode is not None
    }
    for kind in FORM_KIND_PROFILES:
        if kind in declared:
            return kind
    raise ConversionContextError(f"the served Questionnaire `{canonical}` declares no known DHIS2 form kind")


def _identifier_value(questionnaire: Questionnaire, system: str) -> str | None:
    """The DHIS2 identifier one Questionnaire carries under one system, or None when it carries none."""
    for identifier in questionnaire.identifier or []:
        if identifier.system == system and identifier.value:
            return identifier.value
    return None


def _walk(
    items: Sequence[QuestionnaireItem],
    code_system_urls_by_value_set: dict[str, str],
    value_types_by_data_element: dict[str, str],
    questions: dict[str, QuestionSpec],
    group_link_ids: set[str],
) -> None:
    """Collect every question and every group of one item subtree, in document order."""
    for item in items:
        link_id = item.linkId
        if not link_id:
            raise ConversionContextError("the served Questionnaire carries an item with no `linkId`")
        if item.type in _STRUCTURAL_ITEM_TYPES:
            group_link_ids.add(link_id)
        else:
            questions[link_id] = _question(item, link_id, code_system_urls_by_value_set, value_types_by_data_element)
        _walk(item.item or [], code_system_urls_by_value_set, value_types_by_data_element, questions, group_link_ids)


def _question(
    item: QuestionnaireItem,
    link_id: str,
    code_system_urls_by_value_set: dict[str, str],
    value_types_by_data_element: dict[str, str],
) -> QuestionSpec:
    """Read one answerable item into the question spec its answers are serialised through."""
    item_type = item.type or ""
    answer_element = ANSWER_ELEMENTS_BY_ITEM_TYPE.get(item_type)
    base_kind = _WIRE_KINDS_BY_ITEM_TYPE.get(item_type)
    if answer_element is None or base_kind is None:
        raise ConversionContextError(
            f"the served Questionnaire answers `{link_id}` as `{item_type}`, which has no DHIS2 wire spelling"
        )
    data_element_uid, separator, category_option_combo_uid = link_id.partition(CELL_LINK_ID_SEPARATOR)
    repeats = bool(item.repeats)
    value_type = value_types_by_data_element.get(data_element_uid)
    return QuestionSpec(
        link_id=link_id,
        data_element_uid=data_element_uid,
        category_option_combo_uid=category_option_combo_uid if separator else None,
        item_type=item_type,
        answer_element=answer_element,
        wire_kind=_wire_kind(base_kind, repeats=repeats, value_type=value_type),
        repeats=repeats,
        option_system=code_system_urls_by_value_set.get(item.answerValueSet or ""),
        value_type=value_type,
    )


def _wire_kind(base_kind: WireValueKind, *, repeats: bool, value_type: str | None) -> WireValueKind:
    """Refine an item type's wire spelling by what only repetition and the DHIS2 value type can say.

    `MULTI_TEXT` is the one repeating question DHIS2 has, and it stores its selections as one
    comma-joined data value. `TRUE_ONLY` and `BOOLEAN` are the one pair of DHIS2 value types R4
    cannot tell apart, so the distinction survives only when the caller supplied the value type.
    """
    if base_kind == WireValueKind.CODED and repeats:
        return WireValueKind.MULTI_TEXT
    if base_kind == WireValueKind.BOOLEAN and value_type == _TRUE_ONLY_VALUE_TYPE:
        return WireValueKind.TRUE_ONLY
    return base_kind
