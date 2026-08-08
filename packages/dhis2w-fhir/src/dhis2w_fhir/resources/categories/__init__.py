"""Pre-built FHIR JSON for DHIS2 categories: one CodeSystem and one ValueSet document per category.

A DHIS2 category is one axis of a disaggregation and its category options are the values
along that axis, which is the shape of an option set and its options - so a category emits
the same pair, built by the same concept-code assignment, into the same predefined-resource
tree. The publisher loads the documents verbatim, so a registry of hundreds of categories
never enters the FSH compile, and SUSHI fishes a predefined resource by its `name` element,
so each document carries the FSH-style name (`D2CAT_Sex_CS` / `_VS`) a `Canonical(...)`
binding resolves against.

The pair owns `ig/input/resources/categories/` outright: a JSON sync deletes every
unproduced `*.json` in its target directory, so the categories and the option sets each
sweep their own directory and never delete the other's documents.

Every concept carries both DHIS2 identifiers: whichever one is the concept code, the other
rides along as a concept property (`dhis2-code` or `dhis2-id`). With
`concept_code_source = "code"`, category options whose code is not a valid FHIR code fall
back to the UID with a note in the report, and an option with no code left to take - a peer
carries its UID as that peer's DHIS2 code - is skipped with its own note rather than emitted
as a duplicate concept.

Both artifacts of one category carry one identity stem, resolved by
`resolve_identity_stems` under `[generate.naming] source`: with `"id"` the slug is the
category UID verbatim (FHIR ids and file names both permit mixed case, so the emitted id
reads straight back to the DHIS2 object), and with the code sources it is the category's
DHIS2 code, falling back to the UID or refusing the run as the source dictates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.attribute_values import (
    attribute_value_extension_url,
    attribute_value_extensions,
    attribute_value_identifiers,
)
from dhis2w_fhir.i18n import name_translations, translated_element
from dhis2w_fhir.names import (
    FHIR_ID_MAX_LENGTH,
    StemSubject,
    code_or_uid,
    join_id_tokens,
    join_name_segments,
    page_string,
    resolve_identity_stems,
)
from dhis2w_fhir.r4 import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemProperty,
    Element,
    Extension,
    Identifier,
    ValueSet,
    ValueSetCompose,
    ValueSetInclude,
)
from dhis2w_fhir.resources.categories.schemas import (
    CategoryIdentity,
    CategoryIdentityPlan,
    CategoryIn,
)
from dhis2w_fhir.resources.option_sets import build_concepts
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import JsonArtifact, JsonBuild

if TYPE_CHECKING:
    from dhis2w_fhir.attributes import AttributeCodeIndex
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "CATEGORY_DIRECTORY",
    "build_category_artifacts",
    "category_fsh_name",
    "category_identities",
    "max_category_slug_length",
]

#: The `ig/input/resources/` subdirectory the category pairs own outright - one JSON file per resource.
CATEGORY_DIRECTORY = "categories"

# The longest emitted id is `<id-stem><slug>-cs`/`-vs`, so the slug is bounded
# against the actual stem and the FHIR id limit.
_ID_SUFFIX = "-vs"

#: The concept-property declarations, each of which takes its `uri` from the configured identifier base.
_PROPERTY_DECLARATIONS = (
    CodeSystemProperty(code="dhis2-code", description="DHIS2 category option code.", type="string"),
    CodeSystemProperty(code="dhis2-id", description="DHIS2 category option UID.", type="code"),
)


class _CategorySystems(BaseModel):
    """The absolute URLs a pre-built category pair references: its canonical base, identifiers, property base."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    identifier_system: str
    code_identifier_system: str
    property_base: str

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> _CategorySystems:
        """Derive the emitted URLs from the IG canonical plus the `[generate]` identifier system base."""
        identifier_base = config.identifier_system_base
        return cls(
            canonical=canonical,
            identifier_system=f"{identifier_base}/id/category",
            code_identifier_system=f"{identifier_base}/id/category-code",
            property_base=f"{identifier_base}/property",
        )

    def code_system_url(self, code_system_id: str) -> str:
        """Canonical URL of one emitted CodeSystem."""
        return f"{self.canonical}/CodeSystem/{code_system_id}"

    def value_set_url(self, value_set_id: str) -> str:
        """Canonical URL of one emitted ValueSet."""
        return f"{self.canonical}/ValueSet/{value_set_id}"


class _CategoryPair(BaseModel):
    """The two resources one DHIS2 category emits, sharing its identity, title, and publication state."""

    model_config = ConfigDict(frozen=True)

    code_system: CodeSystem
    value_set: ValueSet


class _CategoryNarrative(BaseModel):
    """The elements both halves of a pair carry identically: identifiers, title, and publication state."""

    model_config = ConfigDict(frozen=True)

    identifiers: list[Identifier] = Field(default_factory=list)
    extensions: list[Extension] = Field(default_factory=list)
    title: str
    title_element: Element | None = None
    description: str
    status: IgStatus
    experimental: bool


def category_fsh_name(config: GenerateConfig, segment: str) -> str:
    """FSH name stem for one category: the merged naming tokens, then the resolved stem segment.

    The emitted CodeSystem and ValueSet append `_CS` and `_VS` to it, so `D2CAT_Sex` names the
    pair `D2CAT_Sex_CS` / `D2CAT_Sex_VS`.
    """
    return join_name_segments(f"{config.naming.prefix}{config.naming.category}", segment)


def max_category_slug_length(config: GenerateConfig) -> int:
    """Longest slug that keeps every emitted category id within the FHIR id limit."""
    return FHIR_ID_MAX_LENGTH - len(_id_stem(config)) - len(_ID_SUFFIX)


def category_identities(categories: list[CategoryIn], config: GenerateConfig) -> CategoryIdentityPlan:
    """Assign every category its emitted slug, FSH name, and artifact ids, in emission order.

    The slug is the identity stem `resolve_identity_stems` assigns over the whole selection,
    so both artifacts of one category follow the one resolved segment, and a code-sourced run
    falls back or refuses per the configured source.
    """
    plan = CategoryIdentityPlan()
    id_stem = _id_stem(config)
    resolution = resolve_identity_stems(
        [StemSubject(uid=category.uid, code=category.code, label=category.name) for category in categories],
        config.naming.source,
        "category",
        max_stem_length=max_category_slug_length(config),
    )
    for category in sorted(categories, key=lambda item: (item.name, item.uid)):
        slug = resolution.stem_for(category.uid)
        plan.identities.append(
            CategoryIdentity(
                uid=category.uid,
                name=category.name,
                slug=slug,
                fsh_name=category_fsh_name(config, resolution.fsh_segment_for(category.uid)),
                code_system_id=f"{id_stem}{slug}-cs",
                value_set_id=f"{id_stem}{slug}{_ID_SUFFIX}",
            )
        )
    plan.notes.extend(resolution.notes)
    return plan


def build_category_artifacts(
    categories: list[CategoryIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
) -> JsonBuild:
    """Build one `categories/CodeSystem-<id>.json` and `categories/ValueSet-<id>.json` per category."""
    build = JsonBuild()
    systems = _CategorySystems.from_config(config, canonical)
    extension_url = attribute_value_extension_url(config, canonical)
    plan = category_identities(categories, config)
    by_uid = {category.uid: category for category in categories}
    for identity in plan.identities:
        category = by_uid[identity.uid]
        pair = _build_pair(
            category,
            identity,
            config,
            systems,
            build.notes,
            ig_status=ig_status,
            attribute_codes=attribute_codes,
            extension_url=extension_url,
        )
        build.artifacts.append(_json_artifact(f"CodeSystem-{identity.code_system_id}", pair.code_system))
        build.artifacts.append(_json_artifact(f"ValueSet-{identity.value_set_id}", pair.value_set))
    build.notes.extend(plan.notes)
    return build


def _json_artifact(stem: str, resource: CodeSystem | ValueSet) -> JsonArtifact:
    """Serialise one resource as the category file the predefined-resource loader reads."""
    return JsonArtifact(
        relative_path=f"{CATEGORY_DIRECTORY}/{stem}.json",
        content=f"{resource.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
    )


def _build_pair(
    category: CategoryIn,
    identity: CategoryIdentity,
    config: GenerateConfig,
    systems: _CategorySystems,
    notes: list[str],
    *,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
    extension_url: str,
) -> _CategoryPair:
    """Build the CodeSystem and the ValueSet of one category, reporting what concept assignment raised."""
    concepts = build_concepts(category, config, notes)
    narrative = _narrative(
        category, config, systems, ig_status=ig_status, attribute_codes=attribute_codes, extension_url=extension_url
    )
    code_system_url = systems.code_system_url(identity.code_system_id)
    code_system = CodeSystem(
        id=identity.code_system_id,
        extension=narrative.extensions or None,
        url=code_system_url,
        identifier=narrative.identifiers,
        name=identity.code_system_name,
        title=narrative.title,
        title_element=narrative.title_element,
        description=narrative.description,
        status=narrative.status,
        experimental=narrative.experimental,
        caseSensitive=True,
        content="complete",
        count=len(concepts),
        valueSet=systems.value_set_url(identity.value_set_id),
        property=_declarations(concepts, systems) or None,
        concept=concepts or None,
    )
    value_set = ValueSet(
        id=identity.value_set_id,
        extension=narrative.extensions or None,
        url=systems.value_set_url(identity.value_set_id),
        identifier=narrative.identifiers,
        name=identity.value_set_name,
        title=narrative.title,
        title_element=narrative.title_element,
        description=narrative.description,
        status=narrative.status,
        experimental=narrative.experimental,
        compose=ValueSetCompose(include=[ValueSetInclude(system=code_system_url)]),
    )
    return _CategoryPair(code_system=code_system, value_set=value_set)


def _narrative(
    category: CategoryIn,
    config: GenerateConfig,
    systems: _CategorySystems,
    *,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
    extension_url: str,
) -> _CategoryNarrative:
    """The elements both halves share: both DHIS2 identifiers, the attribute values, the title, the state."""
    code_kind = "category option codes" if config.concept_code_source == "code" else "category option UIDs"
    return _CategoryNarrative(
        identifiers=[
            Identifier(system=systems.identifier_system, value=category.uid),
            Identifier(system=systems.code_identifier_system, value=code_or_uid(category.code, category.uid)),
            *attribute_value_identifiers(category.attribute_values, attribute_codes, config.identifier_system_base),
        ],
        extensions=attribute_value_extensions(category.attribute_values, attribute_codes, extension_url),
        title=page_string(category.name),
        title_element=translated_element(name_translations(category.translations, config.locales)),
        description=page_string(
            f"DHIS2 category {category.name} ({category.uid}). Concept codes are DHIS2 {code_kind}."
        ),
        status=ig_status,
        experimental=experimental_for_status(ig_status),
    )


def _declarations(concepts: list[CodeSystemConcept], systems: _CategorySystems) -> list[CodeSystemProperty]:
    """The CodeSystem-level declaration of every concept property the emitted concepts actually carry."""
    carried = {
        concept_property.code
        for concept in concepts
        for concept_property in concept.property or []
        if concept_property.code is not None
    }
    return [
        declaration.model_copy(update={"uri": f"{systems.property_base}/{declaration.code}"})
        for declaration in _PROPERTY_DECLARATIONS
        if declaration.code in carried
    ]


def _id_stem(config: GenerateConfig) -> str:
    """Build the id stem for category artifacts from the configured naming tokens."""
    joined = join_id_tokens(config.naming.prefix, config.naming.category)
    return f"{joined}-" if joined else ""
