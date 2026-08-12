"""The tracked entity type vocabulary and the resource map published over it.

A DHIS2 tracked entity type is not always a person, and `[generate.tracked_entity_types]` states
only the ones that are not. That keeps a person-tracking project's config empty, but it also means
the resolution lives in a file a consumer of the guide never sees - so the guide publishes it: one
`D2TET_CS` concept per type the run's forms register, displayed under the name the instance holds,
and one `D2TET_CM` row per concept naming the FHIR resource type its registrations are published as.

The fixture carries two types on purpose: a `Specimen` batch the project maps and a `Person` it does
not, which is what makes both branches of the resolution visible in one compiled file.

The SUSHI goldens under `tests/data/r4/` were harvested the way every golden here is: the emitted
`data-dictionary/tracked-entity-types.fsh` of this module's fixture, compiled by SUSHI against an IG
whose `sushi-config.yaml` states `canonical: http://example.org/fhir` and `status: draft`, copied
back byte for byte. They are never edited by hand - when the parity test fails, the builder is what
changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    PublishedTrackedEntityType,
    build_questionnaire_artifacts,
    option_set_identities,
    published_tracked_entity_types,
    tracked_entity_type_subject_type,
    unmapped_tracked_entity_type_notes,
)
from dhis2w_fhir.config import NamingConfig
from dhis2w_fhir.doctor import DoctorOutcome, DoctorPhase, generate_findings, grade
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.notes import GenerateNoteCategory
from dhis2w_fhir.r4 import DEFAULT_SUBJECT_RESOURCE_TYPE, FhirBase
from dhis2w_fhir.resources.questionnaires import DATA_DICTIONARY_DIRECTORY
from dhis2w_fhir.resources.questionnaires.documents import build_data_dictionary_documents
from dhis2w_fhir.resources.questionnaires.schemas import (
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    form_subject_type,
)

_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4"

#: The IG the goldens were compiled for - `[ig] canonical` and `[ig] status` of its `fhir.toml`.
_CANONICAL = "http://example.org/fhir"

#: The emitted file both the vocabulary and the map are written into.
_FILE = f"{DATA_DICTIONARY_DIRECTORY}/tracked-entity-types.fsh"

#: The person-only form of the type this project tracks people as, left unmapped so it stands for
#: the default. It carries a DHIS2 code and a NAME translation, which is what puts a `dhis2-code`
#: property and a designation on one concept and nothing on the other.
_PERSON = QuestionnaireSourceIn(
    uid="Tet1aaaaaaa",
    name="Person",
    code="TET_PERSON",
    kind="tracked-entity",
    tracked_entity_type_uid="Tet1aaaaaaa",
    translations=[TranslationIn(locale="fr", property="NAME", value="Personne")],
    flat_items=[
        QuestionnaireItemIn(uid="Tea1aaaaaaa", name="National identifier", value_type="TEXT", unique=True),
    ],
)

#: The second type the project tracks, which is plainly not a person and is mapped as such.
_SPECIMEN = QuestionnaireSourceIn(
    uid="Tet2aaaaaaa",
    name="Specimen batch",
    kind="tracked-entity",
    tracked_entity_type_uid="Tet2aaaaaaa",
    flat_items=[
        QuestionnaireItemIn(uid="Tea2aaaaaaa", name="Batch number", value_type="TEXT", unique=True),
    ],
)

#: The tracker program that registers the specimen batches, plus one stage of it. Neither publishes
#: a concept of its own - the vocabulary is over types, not over the forms that register them - but
#: both read the same resolution the map's row states.
_SPECIMEN_PROGRAM = QuestionnaireSourceIn(
    uid="Trk1aaaaaaa",
    name="Specimen tracking",
    kind="tracker",
    tracked_entity_type_uid="Tet2aaaaaaa",
    flat_items=[QuestionnaireItemIn(uid="Tea2aaaaaaa", name="Batch number", value_type="TEXT", unique=True)],
)

_SPECIMEN_STAGE = QuestionnaireSourceIn(
    uid="Pst1aaaaaaa",
    name="Analysis",
    kind="tracker-event",
    program=ProgramContextIn(uid="Trk1aaaaaaa", name="Specimen tracking", tracked_entity_type_uid="Tet2aaaaaaa"),
    flat_items=[QuestionnaireItemIn(uid="De01aaaaaaa", name="Result", value_type="TEXT")],
)

_SOURCES = [_PERSON, _SPECIMEN, _SPECIMEN_PROGRAM, _SPECIMEN_STAGE]

#: The `[generate]` table the goldens were built under: one type mapped, one left to the default,
#: and French among the locales so the designations are rendered.
_CONFIG = GenerateConfig(locales=["fr"], tracked_entity_types={"Tet2aaaaaaa": "Specimen"})


def config() -> GenerateConfig:
    """The `[generate]` table this module's fixture is emitted under."""
    return _CONFIG


def sources() -> list[QuestionnaireSourceIn]:
    """The forms this module's fixture publishes, in the order the emitters receive them."""
    return list(_SOURCES)


def fsh(forms: list[QuestionnaireSourceIn] | None = None, generate: GenerateConfig | None = None) -> dict[str, str]:
    """Build the FSH artifacts of the fixture and index them by relative path."""
    resolved = generate or _CONFIG
    build = build_questionnaire_artifacts(
        forms or _SOURCES,
        resolved,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], resolved),
        attribute_codes=AttributeCodeIndex(),
    )
    return {artifact.relative_path: artifact.content for artifact in build.artifacts}


def _notes(forms: list[QuestionnaireSourceIn], generate: GenerateConfig) -> list[str]:
    """The notes one build raised, as the sentences a report prints."""
    build = build_questionnaire_artifacts(
        forms,
        generate,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], generate),
        attribute_codes=AttributeCodeIndex(),
    )
    return [note.message for note in build.notes]


def _documents(generate: GenerateConfig | None = None) -> dict[str, dict[str, Any]]:
    """Every document the JSON dictionary builder publishes for the fixture, keyed by its FHIR id."""
    resolved = generate or _CONFIG
    build = build_data_dictionary_documents(_SOURCES, resolved, _CANONICAL, ig_status="draft")
    documents: list[FhirBase] = [*build.code_systems, *build.value_sets, *build.concept_maps]
    dumped = [_dumped(document) for document in documents]
    return {document["id"]: document for document in dumped}


def _dumped(resource: FhirBase) -> dict[str, Any]:
    """One built resource as the JSON object the writer serialises it to."""
    body: dict[str, Any] = json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))
    return body


def _golden(stem: str) -> Any:
    """One SUSHI-compiled golden, parsed."""
    return json.loads((_GOLDEN_DIRECTORY / f"{stem}.json").read_text(encoding="utf-8"))


def test_the_vocabulary_holds_one_concept_per_published_type() -> None:
    """Both types the run's forms register are concepts, named as the instance names them."""
    content = fsh()[_FILE]
    assert "CodeSystem: D2TET_CS" in content
    assert "Id: d2-tet-cs" in content
    assert '* #Tet1aaaaaaa "Person"' in content
    assert '* #Tet2aaaaaaa "Specimen batch"' in content


def test_a_type_carrying_a_dhis2_code_publishes_it_as_a_concept_property() -> None:
    """The `dhis2-code` property is the attribute pair's, over the objects the forms are about."""
    content = fsh()[_FILE]
    assert "* #Tet1aaaaaaa ^property[+].code = #dhis2-code" in content
    assert '* #Tet1aaaaaaa ^property[=].valueString = "TET_PERSON"' in content
    assert "* #Tet2aaaaaaa ^property[+].code = #dhis2-code" not in content


def test_a_name_translation_rides_as_a_designation_under_the_configured_locale() -> None:
    """Translations reach this vocabulary the way they reach its siblings - as concept designations."""
    content = fsh()[_FILE]
    assert "* #Tet1aaaaaaa ^designation[+].language = #fr" in content
    assert '* #Tet1aaaaaaa ^designation[=].value = "Personne"' in content


def test_a_locale_the_project_does_not_publish_carries_no_designation() -> None:
    """The designations are the configured locales, not every translation the instance holds."""
    narrowed = GenerateConfig(locales=["es"], tracked_entity_types={"Tet2aaaaaaa": "Specimen"})
    assert "^designation" not in fsh(generate=narrowed)[_FILE]


def test_a_vocabulary_whose_types_carry_no_dhis2_code_declares_no_property_at_all() -> None:
    """The FSH writes no property block for it, so the built document must carry no `property` key."""
    uncoded = _SPECIMEN.model_copy(update={"uid": "Tet3aaaaaaa", "tracked_entity_type_uid": "Tet3aaaaaaa"})
    generate = GenerateConfig()
    assert "^property" not in fsh([uncoded], generate)[_FILE]
    build = build_data_dictionary_documents([uncoded], generate, _CANONICAL, ig_status="draft")
    code_system = next(document for document in build.code_systems if document.id == "d2-tet-cs")
    assert "property" not in _dumped(code_system)


def test_the_value_set_includes_the_code_system_whole() -> None:
    """The pair is the support pair's shape: a complete code system and the value set over all of it."""
    content = fsh()[_FILE]
    assert "ValueSet: D2TET_VS" in content
    assert "Id: d2-tet-vs" in content
    assert "* include codes from system D2TET_CS" in content


def test_the_map_states_the_resource_each_published_type_is() -> None:
    """One row per concept: the mapped type lands on its resource, the unmapped one on the default."""
    content = fsh()[_FILE]
    assert "Instance: D2TET_CM" in content
    assert '* id = "d2-tet-cm"' in content
    assert "* group[0].element[0].code = #Tet1aaaaaaa" in content
    assert "* group[0].element[0].target[0].code = #Patient" in content
    assert "* group[0].element[1].code = #Tet2aaaaaaa" in content
    assert "* group[0].element[1].target[0].code = #Specimen" in content


def test_every_row_states_the_equivalence_r4_requires() -> None:
    """`equivalence` is mandatory in R4, and a type and its resource name the same thing."""
    content = fsh()[_FILE]
    assert content.count("target[0].equivalence = #equal") == 2


def test_the_map_is_sourced_from_the_type_vocabulary_and_targets_the_r4_resource_types() -> None:
    """A `$translate` caller reaches the map by the code system the concept it holds came from."""
    content = fsh()[_FILE]
    assert '* group[0].source = "http://example.org/fhir/CodeSystem/d2-tet-cs"' in content
    assert '* group[0].target = "http://hl7.org/fhir/resource-types"' in content
    assert "* sourceCanonical = Canonical(D2TET_VS)" in content
    assert '* targetCanonical = "http://hl7.org/fhir/ValueSet/resource-types"' in content


def test_a_run_with_no_person_only_form_publishes_no_type_vocabulary() -> None:
    """The vocabulary is over the types the run publishes, so a run over data sets alone holds none."""
    aggregate = QuestionnaireSourceIn(
        uid="Ds01aaaaaaa",
        name="Monthly report",
        kind="aggregate",
        flat_items=[QuestionnaireItemIn(uid="De01aaaaaaa", name="Cases", value_type="INTEGER")],
    )
    assert _FILE not in fsh([aggregate], GenerateConfig())
    build = build_data_dictionary_documents([aggregate], GenerateConfig(), _CANONICAL, ig_status="draft")
    assert build.concept_maps == []


@pytest.mark.parametrize("stem", ["CodeSystem-d2-tet-cs", "ValueSet-d2-tet-vs", "ConceptMap-d2-tet-cm"])
def test_the_built_documents_equal_what_sushi_compiled_from_the_same_fsh(stem: str) -> None:
    """The JSON builder and the FSH template publish one vocabulary, key for key."""
    documents = _documents()
    assert documents[stem.split("-", 1)[1]] == _golden(stem)


def test_the_map_row_is_the_subject_type_every_form_of_that_type_declares() -> None:
    """One resolution, read by the map and by the forms: a row and a `subjectType` cannot disagree."""
    rows = {
        element["code"]: element["target"][0]["code"] for element in _documents()["d2-tet-cm"]["group"][0]["element"]
    }
    for source in _SOURCES:
        uid = source.tracked_entity_type_uid or (source.program.tracked_entity_type_uid if source.program else None)
        if uid is None:
            continue
        assert form_subject_type(source, _CONFIG.tracked_entity_types) == rows[uid]


def test_an_unmapped_type_resolves_to_the_default_resource() -> None:
    """The whole of the default, stated once: a type the project never names is a Patient."""
    assert tracked_entity_type_subject_type("Tet1aaaaaaa", _CONFIG.tracked_entity_types) == (
        DEFAULT_SUBJECT_RESOURCE_TYPE
    )
    assert tracked_entity_type_subject_type("Tet2aaaaaaa", _CONFIG.tracked_entity_types) == "Specimen"


def test_the_published_set_is_the_run_person_only_forms_with_the_resource_already_resolved() -> None:
    """The boundary object every consumer reads: identity, instance name, and the resolved resource."""
    published = published_tracked_entity_types(_SOURCES, _CONFIG.tracked_entity_types)
    assert published == [
        PublishedTrackedEntityType(
            uid="Tet1aaaaaaa",
            name="Person",
            code="TET_PERSON",
            translations=[TranslationIn(locale="fr", property="NAME", value="Personne")],
            resource_type="Patient",
            mapped=False,
        ),
        PublishedTrackedEntityType(
            uid="Tet2aaaaaaa",
            name="Specimen batch",
            resource_type="Specimen",
            mapped=True,
        ),
    ]


def test_the_naming_tokens_move_the_whole_family_together() -> None:
    """A project that renames the tracked-entity-type token moves the form and its vocabulary as one."""
    names = QuestionnaireNaming.from_naming(NamingConfig(prefix="DX", tracked_entity_type="EntityType"))
    assert names.tracked_entity_type_code_system == "DXEntityType_CS"
    assert names.tracked_entity_type_code_system_id == "dx-entity-type-cs"
    assert names.tracked_entity_type_value_set == "DXEntityType_VS"
    assert names.tracked_entity_type_resource_map == "DXEntityType_CM"
    assert names.tracked_entity_type_resource_map_id == "dx-entity-type-cm"


def test_one_unmapped_type_stays_silent() -> None:
    """A project tracking people alone maps nothing and is told nothing - that is the ordinary shape."""
    assert (
        unmapped_tracked_entity_type_notes(
            published_tracked_entity_types([_PERSON, _SPECIMEN_PROGRAM], _CONFIG.tracked_entity_types)
        )
        == []
    )
    assert not [message for message in _notes([_PERSON], GenerateConfig()) if "tracked entity types" in message]


def test_several_unmapped_types_are_named_by_instance_name_and_uid() -> None:
    """Two types published as one resource while the instance holds them apart is worth a word."""
    messages = _notes(_SOURCES, GenerateConfig())
    matched = [message for message in messages if "[generate.tracked_entity_types]" in message]
    assert len(matched) == 1
    assert "2 tracked entity types the published forms register are absent" in matched[0]
    assert "all of them are published as Patient" in matched[0]
    assert 'one line each (Tet1aaaaaaa = "Patient")' in matched[0]
    assert "Person (Tet1aaaaaaa)" in matched[0]
    assert "Specimen batch (Tet2aaaaaaa)" in matched[0]


def test_doctor_warns_on_the_run_that_leaves_several_types_unmapped() -> None:
    """The finding is the generate phase's: the note the run raised, graded as a warning."""
    build = build_questionnaire_artifacts(
        _SOURCES,
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], GenerateConfig()),
        attribute_codes=AttributeCodeIndex(),
    )
    findings = generate_findings(build.notes)
    outcome = grade(DoctorPhase.GENERATE, "1 note(s)", findings)
    assert outcome.outcome is DoctorOutcome.WARNED
    unmapped = [finding for finding in findings if finding.subject == GenerateNoteCategory.SELECTION_GAP.value]
    assert any("Person (Tet1aaaaaaa)" in finding.detail for finding in unmapped)
