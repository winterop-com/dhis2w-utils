"""The published map from this instance's own DHIS2 objects onto the IPS sections they feed.

`docs/fhir/design/ips.md` section 5 lays out three sources a section mapping could come from and
the owner took option C: **`fhir.toml` is the input and the ConceptMap is the published output.**
The operator states the mapping once in the file they already edit, `d2w fhir generate` publishes it
beside the vocabularies it maps, and a consumer audits the assignment without ever seeing this
project's config - which is also the shape a cross-instance comparison would later diff
(`docs/fhir/design/harmonization.md`).

**The sources are the DHIS2 identifier namespaces, not the generated concept codes.** A program
stage rides `{base}/id/program-stage` and a data element rides `{base}/id/data-element` - the very
systems the guide publishes those objects under, and the very ones `[ips.sections]` states its
nominations in. `D2Sex_CM` set the precedent for the same reason: a map keyed on anything else
would publish a translation nobody performs, and a generated concept code moves with
`[generate.naming] source` while a UID namespace never does.

**The target is LOINC**, because an IPS section is a LOINC-coded section of a document and nothing
else. `11369-6` is the Immunizations section, which is the one section phase 2 maps; a later
section is another row in the same groups rather than a second map.

**The server performs the file and publishes the map**, exactly as the identity dial does. What
`d2w fhir serve` assembles a summary from is `fhir.toml`, because a project may edit the file
between two generate runs and a server reading a stale artifact would serve a mapping its operator
had already changed. The map is what makes the claim auditable, not what makes it happen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from dhis2w_fhir.names import join_id_tokens, join_name_segments
from dhis2w_fhir.r4 import ConceptMap, ConceptMapGroup, ConceptMapGroupElement, ConceptMapGroupElementTarget
from dhis2w_fhir.resources.option_sets import CONCEPT_MAP_DIRECTORY, concept_map_canonical
from dhis2w_fhir.status import experimental_for_status
from dhis2w_fhir.summary import IMMUNIZATIONS_SECTION, LOINC_SYSTEM
from dhis2w_fhir.writer import JsonArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.ips import SectionMappings
    from dhis2w_fhir.status import IgStatus

__all__ = [
    "SECTION_MAP_DESCRIPTION",
    "SECTION_MAP_TITLE",
    "build_section_concept_map",
    "build_section_concept_map_artifacts",
    "section_map_file_prefix",
    "section_map_id",
    "section_map_name",
]

#: How closely a mapped row matches. `equal` for the reason every other map here states it: the
#: instance said these values belong in this section, and the map publishes that statement rather
#: than grading it.
_MAP_EQUIVALENCE: Literal["equal"] = "equal"

#: The naming token this one map takes, fixed rather than configurable: it names a section of a
#: clinical document and not a DHIS2 object kind, so there is no DHIS2 vocabulary whose token it
#: should follow.
_MAP_TOKEN = "Section"

#: The identifier-system segments the two groups map out of, which are the two kinds of object a
#: section mapping nominates: the stages whose events carry the content, and the elements inside them.
_PROGRAM_STAGE_SEGMENT = "program-stage"
_DATA_ELEMENT_SEGMENT = "data-element"

SECTION_MAP_TITLE = "DHIS2 program stages and data elements as International Patient Summary sections"

SECTION_MAP_DESCRIPTION = (
    "Every DHIS2 program stage and data element this project nominates as feeding a section of an "
    "International Patient Summary, mapped onto that section's LOINC code. DHIS2 states no such "
    "mapping - it marks no data element as an immunisation, a problem, or an allergy - so the rows "
    "are this instance's own statement, made in [ips.sections] and published here so a consumer can "
    "audit which recorded values a served summary carries without holding that file."
)


def section_map_name(config: GenerateConfig) -> str:
    """FSH name of the map under the run's naming tokens (e.g. `D2Section_CM`)."""
    return join_name_segments(f"{config.naming.prefix}{_MAP_TOKEN}", "CM")


def section_map_id(config: GenerateConfig) -> str:
    """FHIR id of the map under the run's naming tokens (e.g. `d2-section-cm`)."""
    return join_id_tokens(config.naming.prefix, _MAP_TOKEN, "cm")


def section_map_file_prefix(config: GenerateConfig) -> str:
    """The file-name prefix this one map owns, which is what its family sweeps by.

    `concept-maps/` holds four families, so none of them owns the directory outright: each
    sweeps the file names its own naming tokens produce and leaves the others alone.
    """
    return f"ConceptMap-{join_id_tokens(config.naming.prefix, _MAP_TOKEN)}"


def build_section_concept_map(
    sections: SectionMappings, config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> ConceptMap | None:
    """Build the map for one project's section nominations, or None where it nominates no section.

    Two groups, one per DHIS2 namespace the nominations are stated in, each row sorted by the UID so
    a regenerate of an unchanged file produces the same bytes whatever order the lists were typed
    in. A namespace the project nominates nothing under gets no group rather than an empty one.
    """
    if not sections.maps_anything():
        return None
    base = config.identifier_system_base
    immunizations = sections.immunizations
    groups = [
        _group(
            f"{base}/id/{_PROGRAM_STAGE_SEGMENT}",
            sorted(immunizations.program_stages),
            IMMUNIZATIONS_SECTION.code,
            IMMUNIZATIONS_SECTION.display,
        ),
        _group(
            f"{base}/id/{_DATA_ELEMENT_SEGMENT}",
            sorted(immunizations.dose_data_elements),
            IMMUNIZATIONS_SECTION.code,
            IMMUNIZATIONS_SECTION.display,
        ),
    ]
    concept_map_id = section_map_id(config)
    return ConceptMap(
        id=concept_map_id,
        url=concept_map_canonical(canonical, concept_map_id),
        name=section_map_name(config),
        title=SECTION_MAP_TITLE,
        description=SECTION_MAP_DESCRIPTION,
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        group=[group for group in groups if group is not None],
    )


def build_section_concept_map_artifacts(
    sections: SectionMappings, config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> list[JsonArtifact]:
    """Build `concept-maps/ConceptMap-<id>.json` for the map, or nothing where there is no map to build."""
    concept_map = build_section_concept_map(sections, config, canonical, ig_status=ig_status)
    if concept_map is None:
        return []
    return [
        JsonArtifact(
            relative_path=f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-{concept_map.id}.json",
            content=f"{concept_map.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
        )
    ]


def _group(source: str, uids: list[str], section_code: str, section_display: str) -> ConceptMapGroup | None:
    """One namespace's rows, or None where this project nominates nothing under it."""
    if not uids:
        return None
    return ConceptMapGroup(
        source=source,
        target=LOINC_SYSTEM,
        element=[
            ConceptMapGroupElement(
                code=uid,
                target=[
                    ConceptMapGroupElementTarget(
                        code=section_code, display=section_display, equivalence=_MAP_EQUIVALENCE
                    )
                ],
            )
            for uid in uids
        ],
    )
