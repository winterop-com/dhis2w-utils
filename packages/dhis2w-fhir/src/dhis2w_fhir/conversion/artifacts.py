"""Reading one project's published IG into the translation context a forward run drains through.

`build_conversion_context` takes plain R4 models; this module is where a project's guide becomes them.
`collect_artifacts` is the one place documents are sorted into the five resource types the translator
reads - Questionnaire, CodeSystem, ValueSet, ConceptMap, and Location - and everything else the guide
publishes is passed over, because nothing in the QR -> DHIS2 direction consults it.

Two ways a guide reaches it. `load_compiled_artifacts` reads the two trees `d2w fhir serve` serves as
one: `ig/fsh-generated/resources`, which SUSHI compiled from the emitted FSH, and `ig/input/resources`,
the predefined registry, terminology, and ConceptMap tree the generate targets wrote as JSON. A project
that has never run SUSHI has neither, and `dhis2w_fhir.service.fetch_live_artifacts` builds the same
documents off the instance instead - the same builders `d2w fhir serve --live` answers reads from - so
a capture UI that needed no build step drains through a forward that needs none either.

How an unreadable document is handled depends on what it is. A **Questionnaire** the R4 models cannot
read fails the collection naming its source: a form quietly skipped turns every response answering it
into an `unknown-form` refusal, which reads as a problem with the data rather than with the guide. The
other four cost only what they carry - a coded answer resolved unchecked, an organisation-unit
reference read as a UID - so an unreadable one is left out and named on `unreadable_resources`, which
the caller reports. A guide is free to hand-write terminology this package has no model for, and one
such document is not worth refusing a whole spool over.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dhis2w_fhir.conversion.context import build_conversion_context, build_form_spec
from dhis2w_fhir.conversion.schemas import CodedAnswerMode, ConversionNaming
from dhis2w_fhir.foundation.schemas import PROGRAM_RULE_NAME_SUB_EXTENSION, PROGRAM_RULE_UID_SUB_EXTENSION
from dhis2w_fhir.r4 import CodeSystem, ConceptMap, Location, Questionnaire, ValueSet

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from dhis2w_fhir.config import FhirProject
    from dhis2w_fhir.conversion.schemas import ConversionContext

__all__ = [
    "COMPILED_RESOURCES_RELATIVE_PATH",
    "TRANSLATED_RESOURCE_TYPES",
    "BoundQuestionUids",
    "CompiledArtifacts",
    "CompiledIgMissingError",
    "ProgramRuleNames",
    "bound_question_uids",
    "build_project_context",
    "collect_artifacts",
    "load_compiled_artifacts",
    "program_rule_names",
]

#: Directory under the IG that SUSHI compiles the emitted FSH into.
COMPILED_RESOURCES_RELATIVE_PATH = "fsh-generated/resources"

#: The form kind whose questions are tracked entity attributes rather than data elements.
_REGISTRATION_FORM_KIND = "tracker"

#: The one resource type an unreadable document fails the load over, because a skipped form refuses
#: every response answering it - and refuses it as a fact about the data rather than about the guide.
_FORM_RESOURCE_TYPE = "Questionnaire"

#: The five resource types the QR -> DHIS2 translator reads, in the order they are collected. A guide
#: publishes far more than this; nothing else is consulted in the response direction.
TRANSLATED_RESOURCE_TYPES: tuple[str, ...] = (_FORM_RESOURCE_TYPE, "CodeSystem", "ValueSet", "ConceptMap", "Location")


class CompiledIgMissingError(LookupError):
    """Raised when a project has no compiled IG to translate captured responses against."""

    def __init__(self, directory: Path) -> None:
        """Carry the refusal naming the missing directory and the two commands that fill it."""
        super().__init__(
            f"no compiled IG at {directory} - run `d2w fhir generate`, then `make sushi` in the project, "
            "and forward again."
        )


class CompiledArtifactReadError(ValueError):
    """Raised when a published resource the translator reads cannot be parsed as its R4 model."""


class CompiledArtifacts(BaseModel):
    """Everything one published guide holds that the QR -> DHIS2 translator reads."""

    model_config = ConfigDict(frozen=True)

    questionnaires: tuple[Questionnaire, ...] = ()
    code_systems: tuple[CodeSystem, ...] = ()
    value_sets: tuple[ValueSet, ...] = ()
    concept_maps: tuple[ConceptMap, ...] = ()
    locations: tuple[Location, ...] = ()
    unreadable_resources: tuple[str, ...] = ()
    """One line per non-form document left out because the R4 models could not read it, naming the file."""

    @property
    def resource_count(self) -> int:
        """How many published resources were kept, across the five types."""
        return (
            len(self.questionnaires)
            + len(self.code_systems)
            + len(self.value_sets)
            + len(self.concept_maps)
            + len(self.locations)
        )


class SourcedDocument(BaseModel):
    """One wire document paired with whatever names it in a diagnostic - a file path, or a builder."""

    model_config = ConfigDict(frozen=True)

    source: str
    body: dict[str, Any]


def load_compiled_artifacts(project: FhirProject) -> CompiledArtifacts:
    """Read one project's compiled IG plus its predefined resource tree into the artifacts the translator reads.

    Compiled resources are read first and the predefined tree second, which is the order the facade
    loads them in, so a project reading its own guide two ways sees one collection.
    """
    compiled_directory = project.ig_directory / COMPILED_RESOURCES_RELATIVE_PATH
    compiled_paths = sorted(compiled_directory.glob("*.json")) if compiled_directory.is_dir() else []
    if not compiled_paths:
        raise CompiledIgMissingError(compiled_directory)
    predefined_directory = project.resources_directory
    predefined_paths = sorted(predefined_directory.rglob("*.json")) if predefined_directory.is_dir() else []
    return collect_artifacts(
        SourcedDocument(source=str(path), body=_read_resource(path)) for path in [*compiled_paths, *predefined_paths]
    )


def collect_artifacts(documents: Iterable[SourcedDocument]) -> CompiledArtifacts:
    """Sort wire documents into the five resource types the QR -> DHIS2 translator reads.

    One collection point for both ways a project's guide reaches the translator: read off disk from
    a compiled build, or built in memory from the instance a `--live` run points at. Anything
    outside `TRANSLATED_RESOURCE_TYPES` is passed over, because nothing in the response direction
    consults it.

    How an unreadable document is handled depends on what it is. A **Questionnaire** the R4 models
    cannot read fails the collection naming its source: a form quietly skipped turns every response
    answering it into an `unknown-form` refusal, which reads as a problem with the data rather than
    with the guide. The other four cost only what they carry - a coded answer resolved unchecked, an
    organisation-unit reference read as a UID - so an unreadable one is left out and named on
    `unreadable_resources`, which the caller reports.
    """
    questionnaires: list[Questionnaire] = []
    code_systems: list[CodeSystem] = []
    value_sets: list[ValueSet] = []
    concept_maps: list[ConceptMap] = []
    locations: list[Location] = []
    unreadable: list[str] = []
    collections: dict[str, tuple[type[BaseModel], list[Any]]] = {
        _FORM_RESOURCE_TYPE: (Questionnaire, questionnaires),
        "CodeSystem": (CodeSystem, code_systems),
        "ValueSet": (ValueSet, value_sets),
        "ConceptMap": (ConceptMap, concept_maps),
        "Location": (Location, locations),
    }
    for document in documents:
        resource_type = str(document.body.get("resourceType"))
        kept = collections.get(resource_type)
        if kept is None:
            continue
        model, collected = kept
        try:
            collected.append(_parse(model, document.body, document.source))
        except CompiledArtifactReadError as error:
            if resource_type == _FORM_RESOURCE_TYPE:
                raise
            unreadable.append(str(error))
    return CompiledArtifacts(
        questionnaires=tuple(questionnaires),
        code_systems=tuple(code_systems),
        value_sets=tuple(value_sets),
        concept_maps=tuple(concept_maps),
        locations=tuple(locations),
        unreadable_resources=tuple(unreadable),
    )


class BoundQuestionUids(BaseModel):
    """The DHIS2 objects one published guide asks questions from, split by the endpoint that types them.

    Both halves feed the same `value_types_by_data_element` table the context takes, because a link
    id names one object whichever kind of form carries it - the split exists only because a data
    element's value type is read from `/api/dataElements` and an attribute's from
    `/api/trackedEntityAttributes`.
    """

    model_config = ConfigDict(frozen=True)

    data_element_uids: tuple[str, ...] = ()
    tracked_entity_attribute_uids: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        """How many DHIS2 objects the published forms ask a question from, across both kinds."""
        return len(self.data_element_uids) + len(self.tracked_entity_attribute_uids)


def bound_question_uids(artifacts: CompiledArtifacts, naming: ConversionNaming) -> BoundQuestionUids:
    """Every DHIS2 object the published forms ask a question from, sorted, read through the link-id grammar.

    The forms are flattened with the very call the context builds them with, so the UIDs asked of the
    instance are exactly the ones a translated answer will be keyed by - a disaggregated cell's
    `<dataElement>.<categoryOptionCombo>` link id contributing its data element once. A tracker
    registration form's link ids are tracked entity attribute UIDs, so they are collected apart:
    they are the same question grammar keyed to a different DHIS2 object, and a different endpoint
    types them.
    """
    data_elements: set[str] = set()
    attributes: set[str] = set()
    for questionnaire in artifacts.questionnaires:
        form = build_form_spec(questionnaire, naming, {}, {})
        collected = attributes if form.form_kind == _REGISTRATION_FORM_KIND else data_elements
        collected.update(question.data_element_uid for question in form.questions.values())
    return BoundQuestionUids(
        data_element_uids=tuple(sorted(data_elements)),
        tracked_entity_attribute_uids=tuple(sorted(attributes)),
    )


class ProgramRuleNames(BaseModel):
    """The DHIS2 program rules a published guide names, keyed by UID, for reading a refusal back.

    DHIS2 refuses a tracker import a rule rejected with `E1300` and names the rule by UID alone. The
    guide published that UID beside the rule's name, so the drain reads the refusal as the name an
    administrator knows the rule by, while the UID stays on the response's own report.
    """

    model_config = ConfigDict(frozen=True)

    names_by_uid: dict[str, str] = Field(default_factory=dict)

    def name_for(self, uid: str) -> str | None:
        """The name one rule is published under, or None for a UID this guide publishes no rule for."""
        return self.names_by_uid.get(uid)


def program_rule_names(artifacts: CompiledArtifacts, naming: ConversionNaming) -> ProgramRuleNames:
    """Every program rule the published forms carry, read off their `D2ProgramRule` extensions.

    Only the rules a form could not express are published this way, which is exactly the set a
    refusal can name: a rule the form did express refuses nothing the form admits.
    """
    names: dict[str, str] = {}
    for questionnaire in artifacts.questionnaires:
        for extension in questionnaire.extension or []:
            if extension.url != naming.program_rule_url:
                continue
            carried = {sub.url: sub for sub in extension.extension or []}
            uid = carried[PROGRAM_RULE_UID_SUB_EXTENSION].valueId if PROGRAM_RULE_UID_SUB_EXTENSION in carried else None
            name = (
                carried[PROGRAM_RULE_NAME_SUB_EXTENSION].valueString
                if PROGRAM_RULE_NAME_SUB_EXTENSION in carried
                else None
            )
            if uid and name:
                names.setdefault(uid, name)
    return ProgramRuleNames(names_by_uid=names)


def build_project_context(
    project: FhirProject,
    artifacts: CompiledArtifacts,
    *,
    value_types_by_data_element: dict[str, str] | None = None,
    coded_answer_mode: CodedAnswerMode = CodedAnswerMode.LENIENT,
) -> ConversionContext:
    """Assemble the translation context one project's captured responses are read through.

    Every name comes from `fhir.toml` - the IG canonical the extensions are pinned to and the
    `[generate]` naming tokens and identifier base - and the project timezone is what a zoned R4
    timestamp is read back through into the wall clock DHIS2 stores (BUGS.md #62).
    """
    generate = project.config.generate
    naming = ConversionNaming.from_config(generate, project.config.ig.canonical)
    return build_conversion_context(
        naming,
        artifacts.questionnaires,
        code_systems=artifacts.code_systems,
        value_sets=artifacts.value_sets,
        concept_maps=artifacts.concept_maps,
        locations=artifacts.locations,
        value_types_by_data_element=value_types_by_data_element,
        coded_answer_mode=coded_answer_mode,
        timezone=generate.timezone,
    )


def _read_resource(path: Path) -> dict[str, Any]:
    """Read one published file as the JSON object a FHIR resource is, failing loudly and naming it."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompiledArtifactReadError(f"{path}: not readable as JSON ({error})") from error
    if not isinstance(body, dict):
        raise CompiledArtifactReadError(f"{path}: expected a JSON object holding a FHIR resource")
    return body


def _parse[T: BaseModel](model: type[T], body: dict[str, Any], source: str) -> T:
    """Validate one published resource against the R4 model the translator reads it as."""
    try:
        return model.model_validate(body)
    except ValidationError as error:
        raise CompiledArtifactReadError(
            f"{source}: the published {model.__name__} carries elements this package cannot read ({error})"
        ) from error
