"""Unit tests for the IG resource store: loading both trees, reads, search semantics, and summary."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir_serve.store import (
    CompiledIgMissingError,
    IdentifierToken,
    ResourceStore,
    SearchQuery,
    StoreEntry,
    load_compiled_store,
)

CANONICAL = "http://example.org/fhir"
PROGRAM_SYSTEM = "http://dhis2.org/fhir/id/program"

WriteResource = Callable[[Path, dict[str, Any]], None]


def test_load_merges_both_trees(compiled_project: FhirProject) -> None:
    """The compiled tree and the predefined resource tree land in one store."""
    store = load_compiled_store(compiled_project)

    assert store.types_present() == (
        "CodeSystem",
        "ImplementationGuide",
        "Organization",
        "Questionnaire",
        "StructureDefinition",
    )
    assert len(store.entries) == 5


def test_load_reads_foreign_resource_types(compiled_project: FhirProject) -> None:
    """Types this repo has no model for load byte-faithfully."""
    store = load_compiled_store(compiled_project)

    structure_definition = store.by_type_and_id("StructureDefinition", "d2-aggregate-response")

    assert structure_definition is not None
    assert structure_definition.body["kind"] == "resource"
    assert structure_definition.source == "ig/fsh-generated/resources/StructureDefinition-d2-aggregate-response.json"


def test_load_records_predefined_source_path(compiled_project: FhirProject) -> None:
    """A predefined resource carries its path under the project, not an absolute one."""
    store = load_compiled_store(compiled_project)

    organization = store.by_type_and_id("Organization", "X")

    assert organization is not None
    assert organization.source == "ig/input/resources/registry/Organization-X.json"


def test_missing_compiled_ig_raises(empty_project: FhirProject) -> None:
    """A project that was never compiled points at the generate-then-sushi sequence."""
    with pytest.raises(CompiledIgMissingError) as raised:
        load_compiled_store(empty_project)

    assert str(raised.value) == (
        "no compiled IG at ig/fsh-generated/resources - run `d2w fhir generate`, "
        "then `make sushi` in the project, and serve again."
    )


def test_empty_compiled_directory_raises(empty_project: FhirProject) -> None:
    """An existing but empty compiled directory is the same failure as a missing one."""
    (empty_project.ig_directory / "fsh-generated" / "resources").mkdir(parents=True)

    with pytest.raises(CompiledIgMissingError):
        load_compiled_store(empty_project)


def test_corrupt_json_fails_loudly_naming_the_file(compiled_project: FhirProject) -> None:
    """Unparseable JSON names the file rather than being skipped."""
    corrupt = compiled_project.ig_directory / "fsh-generated" / "resources" / "Questionnaire-broken.json"
    corrupt.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Questionnaire-broken\.json: not valid JSON"):
        load_compiled_store(compiled_project)


def test_missing_resource_type_fails_loudly_naming_the_file(
    compiled_project: FhirProject, write_resource: WriteResource
) -> None:
    """A JSON object without resourceType names the file."""
    write_resource(
        compiled_project.ig_directory / "fsh-generated" / "resources" / "Nameless.json",
        {"id": "x"},
    )

    with pytest.raises(ValueError, match=r"Nameless\.json: resource has no `resourceType`"):
        load_compiled_store(compiled_project)


def test_missing_id_fails_loudly_naming_the_file(compiled_project: FhirProject, write_resource: WriteResource) -> None:
    """A resource without an id names the file."""
    write_resource(
        compiled_project.ig_directory / "fsh-generated" / "resources" / "Idless.json",
        {"resourceType": "Questionnaire"},
    )

    with pytest.raises(ValueError, match=r"Idless\.json: resource has no `id`"):
        load_compiled_store(compiled_project)


def test_by_type_and_id(compiled_project: FhirProject) -> None:
    """A read resolves by type and id, and misses return None."""
    store = load_compiled_store(compiled_project)

    found = store.by_type_and_id("Questionnaire", "d2-pr-anc-visit-q")

    assert found is not None
    assert found.body["title"] == "ANC Visit"
    assert store.by_type_and_id("Questionnaire", "nope") is None
    assert store.by_type_and_id("Organization", "d2-pr-anc-visit-q") is None


def test_by_canonical(compiled_project: FhirProject) -> None:
    """A canonical url resolves whatever the type, and a resource without a url is unreachable that way."""
    store = load_compiled_store(compiled_project)

    assert store.by_canonical(f"{CANONICAL}/Questionnaire/d2-pr-anc-visit-q") is not None
    assert store.by_canonical(f"{CANONICAL}/StructureDefinition/d2-aggregate-response") is not None
    assert store.by_canonical(f"{CANONICAL}/Organization/X") is None


def test_search_without_parameters_returns_every_resource_of_the_type(compiled_project: FhirProject) -> None:
    """An empty query is a type-wide listing."""
    store = load_compiled_store(compiled_project)

    assert len(store.search("Questionnaire", SearchQuery())) == 1
    assert store.search("Patient", SearchQuery()) == ()


def test_search_by_id_ors_within_the_field(compiled_project: FhirProject, write_resource: WriteResource) -> None:
    """Several ids match either."""
    write_resource(
        compiled_project.ig_directory / "fsh-generated" / "resources" / "Questionnaire-second.json",
        {"resourceType": "Questionnaire", "id": "second", "status": "draft"},
    )
    store = load_compiled_store(compiled_project)

    found = store.search("Questionnaire", SearchQuery(ids=("d2-pr-anc-visit-q", "second")))

    assert {entry.resource_id for entry in found} == {"d2-pr-anc-visit-q", "second"}
    assert store.search("Questionnaire", SearchQuery(ids=("second",)))[0].resource_id == "second"


def test_search_by_url(compiled_project: FhirProject) -> None:
    """A url search matches the canonical, and a resource without one never matches."""
    store = load_compiled_store(compiled_project)

    found = store.search("Questionnaire", SearchQuery(urls=(f"{CANONICAL}/Questionnaire/d2-pr-anc-visit-q",)))

    assert len(found) == 1
    assert store.search("Organization", SearchQuery(urls=(f"{CANONICAL}/Organization/X",))) == ()


def test_search_by_identifier_with_system(compiled_project: FhirProject) -> None:
    """A system-qualified token matches only that system."""
    store = load_compiled_store(compiled_project)

    qualified = SearchQuery(identifiers=(IdentifierToken(system=PROGRAM_SYSTEM, value="ZzYYXq4fJie"),))
    wrong_system = SearchQuery(identifiers=(IdentifierToken(system="http://elsewhere", value="ZzYYXq4fJie"),))

    assert len(store.search("Questionnaire", qualified)) == 1
    assert store.search("Questionnaire", wrong_system) == ()


def test_search_by_identifier_without_system_matches_any_system(compiled_project: FhirProject) -> None:
    """A bare token matches the value in whichever system carries it."""
    store = load_compiled_store(compiled_project)

    bare = SearchQuery(identifiers=(IdentifierToken(value="ZzYYXq4fJie"),))
    bare_on_systemless_resource = SearchQuery(identifiers=(IdentifierToken(value="bare-token-no-system"),))

    assert len(store.search("Questionnaire", bare)) == 1
    assert len(store.search("CodeSystem", bare_on_systemless_resource)) == 1


def test_search_ors_within_the_identifier_field(compiled_project: FhirProject) -> None:
    """Several identifier tokens match either."""
    store = load_compiled_store(compiled_project)

    query = SearchQuery(
        identifiers=(
            IdentifierToken(value="not-in-the-ig"),
            IdentifierToken(system=PROGRAM_SYSTEM, value="ZzYYXq4fJie"),
        )
    )

    assert len(store.search("Questionnaire", query)) == 1


def test_search_ands_across_fields(compiled_project: FhirProject) -> None:
    """Fields combine with AND, so one miss drops the resource."""
    store = load_compiled_store(compiled_project)

    both_match = SearchQuery(
        ids=("d2-pr-anc-visit-q",),
        identifiers=(IdentifierToken(system=PROGRAM_SYSTEM, value="ZzYYXq4fJie"),),
    )
    one_misses = SearchQuery(
        ids=("d2-pr-anc-visit-q",),
        identifiers=(IdentifierToken(value="not-in-the-ig"),),
    )

    assert len(store.search("Questionnaire", both_match)) == 1
    assert store.search("Questionnaire", one_misses) == ()


def test_summary_counts_by_type(compiled_project: FhirProject) -> None:
    """The summary reports one count per type, and totals them."""
    store = load_compiled_store(compiled_project)

    summary = store.summary()

    assert summary.counts_by_type == {
        "CodeSystem": 1,
        "ImplementationGuide": 1,
        "Organization": 1,
        "Questionnaire": 1,
        "StructureDefinition": 1,
    }
    assert summary.total == 5


def test_summary_of_an_empty_store() -> None:
    """A store with no entries summarises to nothing rather than failing."""
    store = ResourceStore()

    assert store.summary().counts_by_type == {}
    assert store.summary().total == 0
    assert store.types_present() == ()


def test_first_entry_wins_on_duplicate_type_and_id() -> None:
    """When both trees carry the same type and id, the first loaded is the one read back."""
    store = ResourceStore(
        entries=(
            StoreEntry(
                resource_type="Questionnaire",
                resource_id="q",
                source="ig/fsh-generated/resources/Questionnaire-q.json",
                body={"resourceType": "Questionnaire", "id": "q", "title": "compiled"},
            ),
            StoreEntry(
                resource_type="Questionnaire",
                resource_id="q",
                source="ig/input/resources/Questionnaire-q.json",
                body={"resourceType": "Questionnaire", "id": "q", "title": "predefined"},
            ),
        )
    )

    found = store.by_type_and_id("Questionnaire", "q")

    assert found is not None
    assert found.body["title"] == "compiled"
