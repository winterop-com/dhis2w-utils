"""Golden tests for the two ConceptMap families - option sets and categories.

Both families answer the same question about a different DHIS2 object kind, so both are held
to the same bar here: the emitted shape, the identity the map rides, and byte parity with what
SUSHI compiles from the same instance authored as FSH.
"""

import json
from pathlib import Path
from typing import Any

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.r4 import ConceptMap
from dhis2w_fhir.resources.categories import (
    build_category_concept_map_artifacts,
    build_category_concept_maps,
    category_concept_map_file_prefix,
    category_identities,
)
from dhis2w_fhir.resources.categories.schemas import CategoryIn
from dhis2w_fhir.resources.option_sets import (
    CONCEPT_MAP_DIRECTORY,
    build_option_set_concept_map_artifacts,
    build_option_set_concept_maps,
    concept_map_canonical,
    option_set_concept_map_file_prefix,
    option_set_identities,
)
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.status import IgStatus

_CODE_STEMS = GenerateConfig(naming=NamingConfig(source="code"))
_CANONICAL = "http://example.org/fhir"

#: The SUSHI-compiled ConceptMap the emitter is held against: the same instance authored as FSH,
#: compiled by SUSHI, and written back out byte for byte identical to what the emitter produces.
_SUSHI_GOLDEN = Path(__file__).parent / "data" / "r4" / "ConceptMap-d2-os-birth-type-cm.json"

#: The category family's twin of that golden, harvested from SUSHI the same way.
_CATEGORY_SUSHI_GOLDEN = Path(__file__).parent / "data" / "r4" / "ConceptMap-d2-cat-sex-cm.json"

_BIRTH_TYPE = OptionSetIn(
    uid="Xa1b2c3d4e5",
    code="birth-type",
    name="Birth type",
    options=[
        OptionIn(uid="EBE0c8sZazS", code="CS", name="Scheduled Cesarean", sort_order=2),
        OptionIn(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1),
        OptionIn(uid="GVcG84DTFOB", code=None, name="Unplanned Cesarean", sort_order=3),
    ],
)

_SEX = CategoryIn(
    uid="O5P6e8yu1T6",
    code="sex",
    name="Sex",
    options=[
        OptionIn(uid="TNYQzTHdoxL", code="F", name="Female", sort_order=0),
        OptionIn(uid="apsOixVZlf1", code="M", name="Male", sort_order=1),
    ],
)

#: The DHIS2 namespaces a category map targets, under the default identifier system base.
_CATEGORY_OPTION_SYSTEM = "http://dhis2.org/fhir/id/category-option"
_CATEGORY_OPTION_CODE_SYSTEM = "http://dhis2.org/fhir/id/category-option-code"


def _maps(option_sets: list[OptionSetIn], config: GenerateConfig, ig_status: IgStatus = "draft") -> list[ConceptMap]:
    """Build the ConceptMaps for one selection against the test canonical."""
    return build_option_set_concept_maps(option_sets, config, _CANONICAL, ig_status=ig_status)


def _category_maps(
    categories: list[CategoryIn], config: GenerateConfig, ig_status: IgStatus = "draft"
) -> list[ConceptMap]:
    """Build the category ConceptMaps for one selection against the test canonical."""
    return build_category_concept_maps(categories, config, _CANONICAL, ig_status=ig_status)


def _document(option_sets: list[OptionSetIn], config: GenerateConfig) -> dict[str, Any]:
    """The first emitted map, serialised the way the emitter writes it and parsed back."""
    dumped: dict[str, Any] = json.loads(_maps(option_sets, config)[0].model_dump_json(exclude_none=True, by_alias=True))
    return dumped


def _category_document(categories: list[CategoryIn], config: GenerateConfig) -> dict[str, Any]:
    """The first emitted category map, serialised the way the emitter writes it and parsed back."""
    dumped: dict[str, Any] = json.loads(
        _category_maps(categories, config)[0].model_dump_json(exclude_none=True, by_alias=True)
    )
    return dumped


def _group(document: dict[str, Any], target_system: str) -> dict[str, Any]:
    """The one group of a map that targets `target_system`."""
    matched: list[dict[str, Any]] = [group for group in document["group"] if group["target"] == target_system]
    assert len(matched) == 1
    return matched[0]


def _rows(group: dict[str, Any]) -> list[tuple[str, str]]:
    """One group's mappings as `(concept code, target code)` pairs, in emission order."""
    return [(element["code"], element["target"][0]["code"]) for element in group["element"]]


def test_the_emitted_map_matches_what_sushi_compiles_from_the_same_instance() -> None:
    """The emitted document is the SUSHI-compiled ConceptMap key for key - the same parity the pairs keep."""
    assert _document([_BIRTH_TYPE], _CODE_STEMS) == json.loads(_SUSHI_GOLDEN.read_text(encoding="utf-8"))


def test_two_groups_resolve_both_dhis2_identifiers_of_every_concept() -> None:
    """A consumer holding one generated coding resolves the DHIS2 option UID and the DHIS2 option code."""
    document = _document([_BIRTH_TYPE], _CODE_STEMS)
    code_system_url = "http://example.org/fhir/CodeSystem/d2-os-birth-type-cs"
    assert [group["source"] for group in document["group"]] == [code_system_url, code_system_url]
    assert _rows(_group(document, "http://dhis2.org/fhir/id/option")) == [
        ("kRRUtYaGett", "kRRUtYaGett"),
        ("EBE0c8sZazS", "EBE0c8sZazS"),
        ("GVcG84DTFOB", "GVcG84DTFOB"),
    ]
    assert _rows(_group(document, "http://dhis2.org/fhir/id/option-code")) == [
        ("kRRUtYaGett", "NB"),
        ("EBE0c8sZazS", "CS"),
    ]


def test_code_source_maps_the_dhis2_code_concept_back_to_its_uid() -> None:
    """With concept codes sourced from DHIS2 codes, the UID group is what a consumer reaches for."""
    document = _document([_BIRTH_TYPE], GenerateConfig(naming=NamingConfig(source="code"), concept_code_source="code"))
    assert _rows(_group(document, "http://dhis2.org/fhir/id/option")) == [
        ("NB", "kRRUtYaGett"),
        ("CS", "EBE0c8sZazS"),
        ("GVcG84DTFOB", "GVcG84DTFOB"),
    ]
    assert _rows(_group(document, "http://dhis2.org/fhir/id/option-code")) == [("NB", "NB"), ("CS", "CS")]


def test_every_mapping_states_the_equivalence_r4_requires() -> None:
    """`equivalence` is mandatory in R4, and both identifiers name the very same DHIS2 option."""
    document = _document([_BIRTH_TYPE], _CODE_STEMS)
    equivalences = {
        target["equivalence"]
        for group in document["group"]
        for element in group["element"]
        for target in element["target"]
    }
    assert equivalences == {"equal"}


def test_a_set_whose_options_carry_no_code_emits_the_uid_group_alone() -> None:
    """A group with no element is invalid R4, so the code group is emitted only when a code exists."""
    uncoded = OptionSetIn(
        uid="Ys9d8f7g6h5",
        code="uncoded",
        name="Uncoded",
        options=[OptionIn(uid="Op1aaaaaaaa", name="One", sort_order=1)],
    )
    document = _document([uncoded], _CODE_STEMS)
    assert [group["target"] for group in document["group"]] == ["http://dhis2.org/fhir/id/option"]


def test_a_code_that_is_not_a_valid_fhir_code_is_left_out_of_the_code_group() -> None:
    """A target code is an R4 `code`, so a DHIS2 code holding a double space cannot be a mapping target."""
    hostile = OptionSetIn(
        uid="Ys9d8f7g6h5",
        code="hostile",
        name="Hostile",
        options=[
            OptionIn(uid="Op1aaaaaaaa", code="A  B", name="One", sort_order=1),
            OptionIn(uid="Op2aaaaaaaa", code="OK", name="Two", sort_order=2),
        ],
    )
    document = _document([hostile], _CODE_STEMS)
    assert _rows(_group(document, "http://dhis2.org/fhir/id/option-code")) == [("Op2aaaaaaaa", "OK")]


def test_an_option_set_without_options_emits_no_map() -> None:
    """A ConceptMap with no group states nothing, so an empty set contributes no document at all."""
    empty = OptionSetIn(uid="Ys9d8f7g6h5", code="sample", name="Sample", options=[])
    assert _maps([empty], _CODE_STEMS) == []
    assert build_option_set_concept_map_artifacts([empty], _CODE_STEMS, _CANONICAL, ig_status="draft") == []


def test_a_skipped_option_is_absent_from_every_group() -> None:
    """An option that received no concept code is not in the CodeSystem, so it is not in the map either."""
    collided = OptionSetIn(
        uid="Ys9d8f7g6h5",
        code="collided",
        name="Collided",
        options=[
            OptionIn(uid="Op2aaaaaaaa", code="Op1aaaaaaaa", name="One", sort_order=1),
            OptionIn(uid="Op1aaaaaaaa", code="Op1aaaaaaaa", name="Two", sort_order=2),
        ],
    )
    document = _document([collided], GenerateConfig(naming=NamingConfig(source="code"), concept_code_source="code"))
    assert _rows(_group(document, "http://dhis2.org/fhir/id/option")) == [("Op1aaaaaaaa", "Op2aaaaaaaa")]


def test_the_map_takes_its_identity_from_the_same_plan_the_pair_does() -> None:
    """Id, name, and URL are the option set's own slug, so all three artifacts of a set stay in step."""
    identity = option_set_identities([_BIRTH_TYPE], _CODE_STEMS).identities[0]
    document = _document([_BIRTH_TYPE], _CODE_STEMS)
    assert identity.concept_map_id == "d2-os-birth-type-cm"
    assert identity.concept_map_name == "D2OS_BirthType_CM"
    assert document["id"] == identity.concept_map_id
    assert document["name"] == identity.concept_map_name
    assert document["url"] == concept_map_canonical(_CANONICAL, identity.concept_map_id)
    assert document["sourceCanonical"] == f"{_CANONICAL}/ValueSet/{identity.value_set_id}"


def test_the_id_source_default_names_the_map_after_the_option_set_id() -> None:
    """Default naming source is the id, mixed case included, exactly as the pair's ids are."""
    document = _document([_BIRTH_TYPE], GenerateConfig())
    assert document["id"] == "d2-os-Xa1b2c3d4e5-cm"
    assert document["name"] == "D2OS_Xa1b2c3d4e5_CM"


def test_the_map_carries_the_option_sets_business_identifier_as_a_single_element() -> None:
    """R4 gives ConceptMap `identifier` 0..1, so the set's UID rides alone rather than as a list."""
    document = _document([_BIRTH_TYPE], _CODE_STEMS)
    assert document["identifier"] == {"system": "http://dhis2.org/fhir/id/option-set", "value": "Xa1b2c3d4e5"}


def test_the_title_carries_the_dhis2_name_translations() -> None:
    """The map is a published artifact like the pair, so its title carries the same translation extensions."""
    translated = OptionSetIn(
        uid="Ys9d8f7g6h5",
        code="birth-type-2",
        name="Birth type",
        translations=[TranslationIn(locale="fr", property="NAME", value="Type de naissance")],
        options=[OptionIn(uid="Op1aaaaaaaa", code="A", name="One", sort_order=1)],
    )
    document = _document([translated], GenerateConfig(locales=["fr"]))
    assert document["_title"]["extension"][0]["extension"][1] == {"url": "content", "valueString": "Type de naissance"}


def test_publication_state_follows_the_ig_status() -> None:
    """The map is definitional, so it takes the IG's status and the experimental flag the pair takes."""
    draft = json.loads(_maps([_BIRTH_TYPE], _CODE_STEMS)[0].model_dump_json(exclude_none=True, by_alias=True))
    active = json.loads(
        _maps([_BIRTH_TYPE], _CODE_STEMS, "active")[0].model_dump_json(exclude_none=True, by_alias=True)
    )
    assert (draft["status"], draft["experimental"]) == ("draft", True)
    assert (active["status"], active["experimental"]) == ("active", False)


def test_the_target_systems_follow_the_configured_identifier_base() -> None:
    """The DHIS2 option namespaces are derived from `[generate] identifier_system_base`, never hard-coded."""
    config = GenerateConfig(naming=NamingConfig(source="code"), identifier_system_base="https://example.org/dhis2")
    document = _document([_BIRTH_TYPE], config)
    assert [group["target"] for group in document["group"]] == [
        "https://example.org/dhis2/id/option",
        "https://example.org/dhis2/id/option-code",
    ]


def test_the_map_urls_follow_the_ig_canonical() -> None:
    """The map, the ValueSet it maps from, and the CodeSystem its groups source are all under the IG canonical."""
    concept_map = build_option_set_concept_maps(
        [_BIRTH_TYPE], _CODE_STEMS, "https://ig.example/fhir", ig_status="draft"
    )[0]
    assert concept_map.url == "https://ig.example/fhir/ConceptMap/d2-os-birth-type-cm"
    assert concept_map.sourceCanonical == "https://ig.example/fhir/ValueSet/d2-os-birth-type-vs"
    assert concept_map.group is not None
    assert concept_map.group[0].source == "https://ig.example/fhir/CodeSystem/d2-os-birth-type-cs"


def test_the_artifacts_land_in_their_own_directory_as_indented_json() -> None:
    """The maps own `concept-maps/` outright, written as the two-space indented JSON the loader reads."""
    artifacts = build_option_set_concept_map_artifacts([_BIRTH_TYPE], _CODE_STEMS, _CANONICAL, ig_status="draft")
    assert [artifact.relative_path for artifact in artifacts] == [
        f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-d2-os-birth-type-cm.json"
    ]
    assert artifacts[0].content.endswith("}\n")
    assert '\n  "id": "d2-os-birth-type-cm",' in artifacts[0].content


def test_one_map_per_option_set_in_the_plans_emission_order() -> None:
    """Maps are emitted in the order identities are assigned, so a run's output is stable across machines."""
    other = OptionSetIn(
        uid="Ab1b2c3d4e5", code="apgar", name="Apgar", options=[OptionIn(uid="Op1aaaaaaaa", name="One")]
    )
    artifacts = build_option_set_concept_map_artifacts([_BIRTH_TYPE, other], _CODE_STEMS, _CANONICAL, ig_status="draft")
    assert [artifact.relative_path for artifact in artifacts] == [
        f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-d2-os-apgar-cm.json",
        f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-d2-os-birth-type-cm.json",
    ]


def test_the_emitted_category_map_matches_what_sushi_compiles_from_the_same_instance() -> None:
    """The category family keeps the same parity bar the option-set family does, against its own golden."""
    assert _category_document([_SEX], _CODE_STEMS) == json.loads(_CATEGORY_SUSHI_GOLDEN.read_text(encoding="utf-8"))


def test_a_category_map_resolves_both_dhis2_identifiers_of_every_concept() -> None:
    """A consumer holding a generated category coding resolves the category-option UID and its DHIS2 code."""
    document = _category_document([_SEX], _CODE_STEMS)
    code_system_url = "http://example.org/fhir/CodeSystem/d2-cat-sex-cs"
    assert [group["source"] for group in document["group"]] == [code_system_url, code_system_url]
    assert _rows(_group(document, _CATEGORY_OPTION_SYSTEM)) == [
        ("TNYQzTHdoxL", "TNYQzTHdoxL"),
        ("apsOixVZlf1", "apsOixVZlf1"),
    ]
    assert _rows(_group(document, _CATEGORY_OPTION_CODE_SYSTEM)) == [("TNYQzTHdoxL", "F"), ("apsOixVZlf1", "M")]


def test_the_category_target_namespaces_are_the_category_option_ones() -> None:
    """A category option is its own DHIS2 object kind, so the map names it rather than borrowing `id/option`."""
    document = _category_document([_SEX], _CODE_STEMS)
    assert [group["target"] for group in document["group"]] == [
        _CATEGORY_OPTION_SYSTEM,
        _CATEGORY_OPTION_CODE_SYSTEM,
    ]


def test_the_category_code_source_maps_the_dhis2_code_concept_back_to_its_uid() -> None:
    """With concept codes sourced from DHIS2 codes, the UID group is what a consumer reaches for."""
    document = _category_document(
        [_SEX], GenerateConfig(naming=NamingConfig(source="code"), concept_code_source="code")
    )
    assert _rows(_group(document, _CATEGORY_OPTION_SYSTEM)) == [("F", "TNYQzTHdoxL"), ("M", "apsOixVZlf1")]
    assert _rows(_group(document, _CATEGORY_OPTION_CODE_SYSTEM)) == [("F", "F"), ("M", "M")]


def test_every_category_mapping_states_the_equivalence_r4_requires() -> None:
    """`equivalence` is mandatory in R4, and both identifiers name the very same DHIS2 category option."""
    document = _category_document([_SEX], _CODE_STEMS)
    equivalences = {
        target["equivalence"]
        for group in document["group"]
        for element in group["element"]
        for target in element["target"]
    }
    assert equivalences == {"equal"}


def test_a_category_whose_options_carry_no_code_emits_the_uid_group_alone() -> None:
    """A group with no element is invalid R4, so the code group is emitted only when a code exists."""
    uncoded = CategoryIn(
        uid="Ys9d8f7g6h5",
        code="uncoded",
        name="Uncoded",
        options=[OptionIn(uid="Op1aaaaaaaa", name="One", sort_order=0)],
    )
    document = _category_document([uncoded], _CODE_STEMS)
    assert [group["target"] for group in document["group"]] == [_CATEGORY_OPTION_SYSTEM]


def test_a_category_option_code_that_is_not_a_valid_fhir_code_is_left_out_of_the_code_group() -> None:
    """A target code is an R4 `code`, so a DHIS2 category-option code holding a line break cannot be one."""
    hostile = CategoryIn(
        uid="Ys9d8f7g6h5",
        code="hostile",
        name="Hostile",
        options=[
            OptionIn(uid="Op1aaaaaaaa", code="OUTREACH\nOUTREACH", name="One", sort_order=0),
            OptionIn(uid="Op2aaaaaaaa", code="OK", name="Two", sort_order=1),
        ],
    )
    document = _category_document([hostile], _CODE_STEMS)
    assert _rows(_group(document, _CATEGORY_OPTION_CODE_SYSTEM)) == [("Op2aaaaaaaa", "OK")]


def test_a_category_without_options_emits_no_map() -> None:
    """A ConceptMap with no group states nothing, so an empty category contributes no document at all."""
    empty = CategoryIn(uid="Ys9d8f7g6h5", code="sample", name="Sample", options=[])
    assert _category_maps([empty], _CODE_STEMS) == []
    assert build_category_concept_map_artifacts([empty], _CODE_STEMS, _CANONICAL, ig_status="draft") == []


def test_a_skipped_category_option_is_absent_from_every_group() -> None:
    """An option that received no concept code is not in the CodeSystem, so it is not in the map either."""
    collided = CategoryIn(
        uid="Ys9d8f7g6h5",
        code="collided",
        name="Collided",
        options=[
            OptionIn(uid="Op2aaaaaaaa", code="Op1aaaaaaaa", name="One", sort_order=0),
            OptionIn(uid="Op1aaaaaaaa", code="Op1aaaaaaaa", name="Two", sort_order=1),
        ],
    )
    document = _category_document(
        [collided], GenerateConfig(naming=NamingConfig(source="code"), concept_code_source="code")
    )
    assert _rows(_group(document, _CATEGORY_OPTION_SYSTEM)) == [("Op1aaaaaaaa", "Op2aaaaaaaa")]


def test_the_category_map_takes_its_identity_from_the_same_plan_the_pair_does() -> None:
    """Id, name, and URL are the category's own slug, so all three artifacts of a category stay in step."""
    identity = category_identities([_SEX], _CODE_STEMS).identities[0]
    document = _category_document([_SEX], _CODE_STEMS)
    assert identity.concept_map_id == "d2-cat-sex-cm"
    assert identity.concept_map_name == "D2CAT_Sex_CM"
    assert document["id"] == identity.concept_map_id
    assert document["name"] == identity.concept_map_name
    assert document["url"] == concept_map_canonical(_CANONICAL, identity.concept_map_id)
    assert document["sourceCanonical"] == f"{_CANONICAL}/ValueSet/{identity.value_set_id}"


def test_the_id_source_default_names_the_category_map_after_the_category_id() -> None:
    """Default naming source is the id, mixed case included, exactly as the pair's ids are."""
    document = _category_document([_SEX], GenerateConfig())
    assert document["id"] == "d2-cat-O5P6e8yu1T6-cm"
    assert document["name"] == "D2CAT_O5P6e8yu1T6_CM"


def test_the_category_map_carries_the_categorys_business_identifier_as_a_single_element() -> None:
    """R4 gives ConceptMap `identifier` 0..1, so the category's UID rides alone under `id/category`."""
    document = _category_document([_SEX], _CODE_STEMS)
    assert document["identifier"] == {"system": "http://dhis2.org/fhir/id/category", "value": "O5P6e8yu1T6"}


def test_the_category_map_title_carries_the_dhis2_name_translations() -> None:
    """The map is a published artifact like the pair, so its title carries the same translation extensions."""
    translated = CategoryIn(
        uid="Ys9d8f7g6h5",
        code="sex-2",
        name="Sex",
        translations=[TranslationIn(locale="fr", property="NAME", value="Sexe")],
        options=[OptionIn(uid="Op1aaaaaaaa", code="A", name="One", sort_order=0)],
    )
    document = _category_document([translated], GenerateConfig(locales=["fr"]))
    assert document["_title"]["extension"][0]["extension"][1] == {"url": "content", "valueString": "Sexe"}


def test_category_publication_state_follows_the_ig_status() -> None:
    """The map is definitional, so it takes the IG's status and the experimental flag the pair takes."""
    draft = json.loads(_category_maps([_SEX], _CODE_STEMS)[0].model_dump_json(exclude_none=True, by_alias=True))
    active = json.loads(
        _category_maps([_SEX], _CODE_STEMS, "active")[0].model_dump_json(exclude_none=True, by_alias=True)
    )
    assert (draft["status"], draft["experimental"]) == ("draft", True)
    assert (active["status"], active["experimental"]) == ("active", False)


def test_the_category_target_systems_follow_the_configured_identifier_base() -> None:
    """The DHIS2 category-option namespaces are derived from `[generate] identifier_system_base`."""
    config = GenerateConfig(naming=NamingConfig(source="code"), identifier_system_base="https://example.org/dhis2")
    document = _category_document([_SEX], config)
    assert [group["target"] for group in document["group"]] == [
        "https://example.org/dhis2/id/category-option",
        "https://example.org/dhis2/id/category-option-code",
    ]


def test_the_category_map_urls_follow_the_ig_canonical() -> None:
    """The map, the ValueSet it maps from, and the CodeSystem its groups source are all under the IG canonical."""
    concept_map = build_category_concept_maps([_SEX], _CODE_STEMS, "https://ig.example/fhir", ig_status="draft")[0]
    assert concept_map.url == "https://ig.example/fhir/ConceptMap/d2-cat-sex-cm"
    assert concept_map.sourceCanonical == "https://ig.example/fhir/ValueSet/d2-cat-sex-vs"
    assert concept_map.group is not None
    assert concept_map.group[0].source == "https://ig.example/fhir/CodeSystem/d2-cat-sex-cs"


def test_the_category_maps_land_in_the_shared_concept_map_directory() -> None:
    """Both families publish into `concept-maps/`, so one publisher glob covers the whole terminology story."""
    artifacts = build_category_concept_map_artifacts([_SEX], _CODE_STEMS, _CANONICAL, ig_status="draft")
    assert [artifact.relative_path for artifact in artifacts] == [
        f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-d2-cat-sex-cm.json"
    ]
    assert artifacts[0].content.endswith("}\n")
    assert '\n  "id": "d2-cat-sex-cm",' in artifacts[0].content


def test_one_category_map_per_category_in_the_plans_emission_order() -> None:
    """Maps are emitted in the order identities are assigned, so a run's output is stable across machines."""
    other = CategoryIn(
        uid="Ab1b2c3d4e5", code="age", name="Age", options=[OptionIn(uid="Op1aaaaaaaa", name="One", sort_order=0)]
    )
    artifacts = build_category_concept_map_artifacts([_SEX, other], _CODE_STEMS, _CANONICAL, ig_status="draft")
    assert [artifact.relative_path for artifact in artifacts] == [
        f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-d2-cat-age-cm.json",
        f"{CONCEPT_MAP_DIRECTORY}/ConceptMap-d2-cat-sex-cm.json",
    ]


def test_the_two_families_sweep_disjoint_file_prefixes_of_the_shared_directory() -> None:
    """Neither family owns `concept-maps/` outright, so each sweeps only the ids its own naming tokens produce."""
    config = GenerateConfig()
    assert option_set_concept_map_file_prefix(config) == "ConceptMap-d2-os-"
    assert category_concept_map_file_prefix(config) == "ConceptMap-d2-cat-"
    option_set_artifact = build_option_set_concept_map_artifacts([_BIRTH_TYPE], config, _CANONICAL, ig_status="draft")[
        0
    ]
    category_artifact = build_category_concept_map_artifacts([_SEX], config, _CANONICAL, ig_status="draft")[0]
    assert Path(option_set_artifact.relative_path).name.startswith(option_set_concept_map_file_prefix(config))
    assert Path(category_artifact.relative_path).name.startswith(category_concept_map_file_prefix(config))
