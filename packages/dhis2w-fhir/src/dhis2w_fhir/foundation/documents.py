"""JSON emission for the foundation terminology: the form-type and the period-type CodeSystem/ValueSet pairs.

The twin of the terminology `d2-form-type.fsh` and `d2-period.fsh` declare and SUSHI compiles.
Both vocabularies are static - `FORM_TYPE_DEFINITIONS` and `PERIOD_TYPE_DEFINITIONS` - and the FSH
templates render the same Python data these builders do, so the pair a project serves without ever
compiling its guide is the pair a compiled one publishes, concept for concept and word for word.

`build_terminology_pair` is the shared shape behind every pair built here and in
`resources.organisation_units.documents`: a `#complete` CodeSystem carrying its own count and the
canonical of the ValueSet that includes it whole, and that ValueSet composing the CodeSystem back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import (
    FORM_TYPE_DEFINITIONS,
    FORM_TYPE_TERMINOLOGY,
    PERIOD_TYPE_TERMINOLOGY,
    FoundationNaming,
)
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.r4 import CodeSystem, CodeSystemConcept, CodeSystemProperty, ValueSet, ValueSetCompose, ValueSetInclude
from dhis2w_fhir.resources.option_sets import code_system_canonical, value_set_canonical
from dhis2w_fhir.status import IgStatus, experimental_for_status

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.foundation.schemas import TerminologyPairProfile


class TerminologyPair(BaseModel):
    """The CodeSystem and the ValueSet one terminology pair publishes, over the same concepts."""

    model_config = ConfigDict(frozen=True)

    code_system: CodeSystem
    value_set: ValueSet


class FoundationTerminologyBuild(BaseModel):
    """The foundation vocabularies as served documents: the form-type pair, then the period-type pair."""

    model_config = ConfigDict(frozen=True)

    code_systems: list[CodeSystem] = Field(default_factory=list)
    value_sets: list[ValueSet] = Field(default_factory=list)


def build_foundation_terminology_documents(
    config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> FoundationTerminologyBuild:
    """Build the two config-only vocabularies every generated guide publishes, as the documents it serves.

    The form-type pair backs the required binding of the D2FormType extension every Questionnaire
    and every captured response carries; the period-type pair backs the one an aggregate response's
    reporting period is expressed in. Neither depends on a DHIS2 instance, so both are the same
    documents for every project sharing a canonical and a status.
    """
    names = FoundationNaming.from_naming(config.naming)
    pairs = [
        build_terminology_pair(
            [CodeSystemConcept(code=form_type.code, display=form_type.display) for form_type in FORM_TYPE_DEFINITIONS],
            FORM_TYPE_TERMINOLOGY,
            canonical,
            code_system_name=names.form_type_code_system,
            code_system_id=names.form_type_code_system_id,
            value_set_name=names.form_type_value_set,
            value_set_id=names.form_type_value_set_id,
            ig_status=ig_status,
        ),
        build_terminology_pair(
            [
                CodeSystemConcept(code=period_type.name, display=period_type.display)
                for period_type in PERIOD_TYPE_DEFINITIONS
            ],
            PERIOD_TYPE_TERMINOLOGY,
            canonical,
            code_system_name=names.period_type_code_system,
            code_system_id=names.period_type_code_system_id,
            value_set_name=names.period_type_value_set,
            value_set_id=names.period_type_value_set_id,
            ig_status=ig_status,
        ),
    ]
    return FoundationTerminologyBuild(
        code_systems=[pair.code_system for pair in pairs],
        value_sets=[pair.value_set for pair in pairs],
    )


def build_terminology_pair(
    concepts: list[CodeSystemConcept],
    terminology: TerminologyPairProfile,
    canonical: str,
    *,
    code_system_name: str,
    code_system_id: str,
    value_set_name: str,
    value_set_id: str,
    ig_status: IgStatus,
    properties: list[CodeSystemProperty] | None = None,
) -> TerminologyPair:
    """Build one pair: a complete CodeSystem over the concepts, and the ValueSet including it whole.

    `count` is stated because SUSHI states it on every `#complete` CodeSystem it compiles, and a
    served document that omitted it would differ from the compiled one by a key.
    """
    code_system_url = code_system_canonical(canonical, code_system_id)
    value_set_url = value_set_canonical(canonical, value_set_id)
    experimental = experimental_for_status(ig_status)
    return TerminologyPair(
        code_system=CodeSystem(
            id=code_system_id,
            url=code_system_url,
            name=code_system_name,
            title=terminology.title,
            description=terminology.description,
            status=ig_status,
            experimental=experimental,
            caseSensitive=True,
            content="complete",
            count=len(concepts),
            valueSet=value_set_url,
            property=properties,
            concept=concepts,
        ),
        value_set=ValueSet(
            id=value_set_id,
            url=value_set_url,
            name=value_set_name,
            title=terminology.title,
            description=terminology.value_set_text,
            status=ig_status,
            experimental=experimental,
            compose=ValueSetCompose(include=[ValueSetInclude(system=code_system_url)]),
        ),
    )
