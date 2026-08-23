"""The published map from one instance's sex values onto R4's `administrative-gender` codes.

`Patient.gender` is bound to `http://hl7.org/fhir/administrative-gender` with a **required**
binding, and DHIS2's answer to the same question is an option code out of an option set. So the step
between them is a ConceptMap rather than a rename, and `docs/fhir/design/ips.md` section 4 names it
the smallest possible instance of the clinical-vocabulary source section 3 says does not exist yet:
four codes rather than forty thousand. It is the first map this project publishes onto a vocabulary
that is not DHIS2's own, which is the line the whole IPS effort needs and the reason phase 1 spends
it here.

**The source is the attribute's own value namespace**, `{base}/tracked-entity-attribute/{uid}` -
the very system the register publishes that attribute's values under. That is what makes the map
true of what the server does: the server holds a person's value, not an option-set concept, and a
map keyed on anything else would publish a translation nobody performs. The keys are therefore the
values DHIS2 stores against the nominated attribute, which on an option-set-bound attribute is the
option's DHIS2 code.

`[ips.identity]` is the input and this map is the published output, in the manner
`[generate.tracked_entity_types]` and `D2TET_CM` already establish: a consumer resolves a served
`gender` back to the DHIS2 value behind it without holding this project's `fhir.toml`. The register
itself performs the file rather than the map, and so does the section map beside it
(`dhis2w_fhir.resources.ips_sections`): a project may edit `fhir.toml` between two generate runs,
and a server reading a stale artifact would serve a mapping its operator had already changed. What
the map buys is that the claim is auditable, not that it is what happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from dhis2w_fhir.foundation.tracked_entity_attribute_values import tracked_entity_attribute_identifier_system
from dhis2w_fhir.ips import (
    ADMINISTRATIVE_GENDER_CODE_SYSTEM_URL,
    ADMINISTRATIVE_GENDER_VALUE_SET_URL,
)
from dhis2w_fhir.names import join_id_tokens, join_name_segments
from dhis2w_fhir.r4 import ConceptMap, ConceptMapGroup, ConceptMapGroupElement, ConceptMapGroupElementTarget
from dhis2w_fhir.resources.option_sets import CONCEPT_MAP_DIRECTORY, concept_map_canonical
from dhis2w_fhir.status import experimental_for_status
from dhis2w_fhir.writer import JsonArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.ips import IdentityNominations
    from dhis2w_fhir.status import IgStatus

__all__ = [
    "ADMINISTRATIVE_GENDER_MAP_DESCRIPTION",
    "ADMINISTRATIVE_GENDER_MAP_TITLE",
    "administrative_gender_map_file_prefix",
    "administrative_gender_map_id",
    "administrative_gender_map_name",
    "build_administrative_gender_concept_map",
    "build_administrative_gender_concept_map_artifacts",
]

#: How closely a mapped row matches. `equal` for the same reason every other map here states it: the
#: instance said this value means this gender, and the map publishes that statement rather than
#: grading it.
_MAP_EQUIVALENCE: Literal["equal"] = "equal"

#: The naming token this one map takes, fixed rather than configurable: it names a demographic fact
#: and not a DHIS2 object kind, so there is no DHIS2 vocabulary whose token it should follow.
_MAP_TOKEN = "Sex"

ADMINISTRATIVE_GENDER_MAP_TITLE = "DHIS2 sex values as FHIR administrative gender codes"

ADMINISTRATIVE_GENDER_MAP_DESCRIPTION = (
    "Every value of the tracked entity attribute this project nominates as a person's sex, mapped "
    "onto the R4 administrative-gender code the register publishes as Patient.gender. DHIS2 states "
    "no such mapping, so the rows are this instance's own statement, made in [ips.identity] and "
    "published here so a consumer resolves a served gender without holding that file."
)


def administrative_gender_map_name(config: GenerateConfig) -> str:
    """FSH name of the map under the run's naming tokens (e.g. `D2Sex_CM`)."""
    return join_name_segments(f"{config.naming.prefix}{_MAP_TOKEN}", "CM")


def administrative_gender_map_id(config: GenerateConfig) -> str:
    """FHIR id of the map under the run's naming tokens (e.g. `d2-sex-cm`)."""
    return join_id_tokens(config.naming.prefix, _MAP_TOKEN, "cm")


def administrative_gender_map_file_prefix(config: GenerateConfig) -> str:
    """The file-name prefix this one map owns, which is what its family sweeps by.

    `concept-maps/` holds four families, so none of them owns the directory outright: each
    sweeps the file names its own naming tokens produce and leaves the others alone.
    """
    return f"ConceptMap-{join_id_tokens(config.naming.prefix, _MAP_TOKEN)}"


def build_administrative_gender_concept_map(
    identity: IdentityNominations, config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> ConceptMap | None:
    """Build the map for one project's nominations, or None where it nominates no sex attribute.

    One group: the nominated attribute's value namespace onto `administrative-gender`, one row per
    value the table states, sorted by the DHIS2 value so a regenerate of an unchanged file produces
    the same bytes whatever order the keys were typed in.
    """
    if identity.sex is None or not identity.administrative_gender:
        return None
    concept_map_id = administrative_gender_map_id(config)
    return ConceptMap(
        id=concept_map_id,
        url=concept_map_canonical(canonical, concept_map_id),
        name=administrative_gender_map_name(config),
        title=ADMINISTRATIVE_GENDER_MAP_TITLE,
        description=ADMINISTRATIVE_GENDER_MAP_DESCRIPTION,
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        targetCanonical=ADMINISTRATIVE_GENDER_VALUE_SET_URL,
        group=[
            ConceptMapGroup(
                source=tracked_entity_attribute_identifier_system(config.identifier_system_base, identity.sex),
                target=ADMINISTRATIVE_GENDER_CODE_SYSTEM_URL,
                element=[
                    ConceptMapGroupElement(
                        code=dhis2_value,
                        target=[ConceptMapGroupElementTarget(code=gender, equivalence=_MAP_EQUIVALENCE)],
                    )
                    for dhis2_value, gender in sorted(identity.administrative_gender.items())
                ],
            )
        ],
    )


def build_administrative_gender_concept_map_artifacts(
    identity: IdentityNominations, config: GenerateConfig, canonical: str, *, ig_status: IgStatus
) -> list[JsonArtifact]:
    """Build `concept-maps/ConceptMap-<id>.json` for the map, or nothing where there is no map to build."""
    concept_map = build_administrative_gender_concept_map(identity, config, canonical, ig_status=ig_status)
    if concept_map is None:
        return []
    return [
        JsonArtifact(
            relative_path=f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-{concept_map.id}.json",
            content=f"{concept_map.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
        )
    ]
