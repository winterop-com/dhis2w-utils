"""Reading one project's published IG off disk into the translation context a forward run drains through.

`build_conversion_context` takes plain R4 models; this module is where a project's own files become
them. It reads the two trees `d2w fhir serve` serves as one - `ig/fsh-generated/resources`, which SUSHI
compiled from the emitted FSH, and `ig/input/resources`, the predefined registry, terminology, and
ConceptMap tree the generate targets wrote as JSON - and keeps the five resource types the translator
reads: Questionnaire, CodeSystem, ValueSet, ConceptMap, and Location. Everything else the guide
publishes is passed over, because nothing in the QR -> DHIS2 direction consults it.

How an unreadable file is handled depends on what it is. A **Questionnaire** the R4 models cannot read
fails the load naming the file: a form quietly skipped turns every response answering it into an
`unknown-form` refusal, which reads as a problem with the data rather than with the guide. The other
four cost only what they carry - a coded answer resolved unchecked, an organisation-unit reference read
as a UID - so an unreadable one is left out and named on `unreadable_resources`, which the caller
reports. A guide is free to hand-write terminology this package has no model for, and one such document
is not worth refusing a whole spool over.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, ValidationError

from dhis2w_fhir.conversion.context import build_conversion_context, build_form_spec
from dhis2w_fhir.conversion.schemas import CodedAnswerMode, ConversionNaming
from dhis2w_fhir.r4 import CodeSystem, ConceptMap, Location, Questionnaire, ValueSet

if TYPE_CHECKING:
    from pathlib import Path

    from dhis2w_fhir.config import FhirProject
    from dhis2w_fhir.conversion.schemas import ConversionContext

__all__ = [
    "COMPILED_RESOURCES_RELATIVE_PATH",
    "CompiledArtifacts",
    "CompiledIgMissingError",
    "bound_data_element_uids",
    "build_project_context",
    "load_compiled_artifacts",
]

#: Directory under the IG that SUSHI compiles the emitted FSH into.
COMPILED_RESOURCES_RELATIVE_PATH = "fsh-generated/resources"

#: The one resource type an unreadable document fails the load over, because a skipped form refuses
#: every response answering it - and refuses it as a fact about the data rather than about the guide.
_FORM_RESOURCE_TYPE = "Questionnaire"


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
    for path in [*compiled_paths, *predefined_paths]:
        body = _read_resource(path)
        resource_type = str(body.get("resourceType"))
        kept = collections.get(resource_type)
        if kept is None:
            continue
        model, collected = kept
        try:
            collected.append(_parse(model, body, path))
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


def bound_data_element_uids(artifacts: CompiledArtifacts, naming: ConversionNaming) -> tuple[str, ...]:
    """Every DHIS2 data element the published forms bind, sorted, read through the link-id grammar itself.

    The forms are flattened with the very call the context builds them with, so the UIDs asked of the
    instance are exactly the ones a translated answer will be keyed by - a disaggregated cell's
    `<dataElement>.<categoryOptionCombo>` link id contributing its data element once.
    """
    uids = {
        question.data_element_uid
        for questionnaire in artifacts.questionnaires
        for question in build_form_spec(questionnaire, naming, {}, {}).questions.values()
    }
    return tuple(sorted(uids))


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


def _parse[T: BaseModel](model: type[T], body: dict[str, Any], path: Path) -> T:
    """Validate one published resource against the R4 model the translator reads it as."""
    try:
        return model.model_validate(body)
    except ValidationError as error:
        raise CompiledArtifactReadError(
            f"{path}: the published {model.__name__} carries elements this package cannot read ({error})"
        ) from error
