"""The generate-note taxonomy: every emission site's kind, and the validate-echo split it drives."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from dhis2w_fhir.notes import (
    VALIDATE_ECHO_CATEGORIES,
    GenerateNote,
    GenerateNoteCategory,
    aggregate_generate_note,
    aggregate_note,
    generate_note,
)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "dhis2w_fhir"

#: The two constructors a note is allowed to come from - everything else would be an untyped note.
_NOTE_CONSTRUCTORS = frozenset({"generate_note", "aggregate_generate_note"})

#: Every place the package raises a note, by module and kind, with how many sites each pair holds.
#:
#: This is the inventory that keeps the taxonomy honest: a new note has to be classified into a kind
#: and recorded here, and a note that quietly changes kind fails the run. Adding a line is the point,
#: not an obstacle - it is where the author of a new note decides whether validate already says it.
_EMISSION_INVENTORY: dict[str, dict[GenerateNoteCategory, int]] = {
    "hostile_names.py": {GenerateNoteCategory.NAME_SUBSTITUTION: 1, GenerateNoteCategory.CODE_SUBSTITUTION: 1},
    "names.py": {GenerateNoteCategory.STEM_FALLBACK: 1},
    "resources/examples/__init__.py": {
        GenerateNoteCategory.ANSWER_FALLBACK: 1,
        GenerateNoteCategory.INSTANCE_DATA_GAP: 5,
        GenerateNoteCategory.SELECTION_GAP: 1,
        GenerateNoteCategory.SKIPPED_QUESTION: 4,
    },
    "resources/categories/decomposition.py": {GenerateNoteCategory.SELECTION_GAP: 1},
    "resources/examples/documents.py": {GenerateNoteCategory.SELECTION_GAP: 1},
    "resources/option_sets/__init__.py": {
        GenerateNoteCategory.CODE_COLLISION: 2,
        GenerateNoteCategory.CODE_FALLBACK: 1,
    },
    "resources/organisation_units/organization.py": {GenerateNoteCategory.SELECTION_GAP: 1},
    "resources/questionnaires/assignments.py": {GenerateNoteCategory.SELECTION_GAP: 1},
    "resources/questionnaires/__init__.py": {
        GenerateNoteCategory.REFUSED_FORM: 1,
        GenerateNoteCategory.SELECTION_GAP: 1,
    },
    "resources/questionnaires/documents.py": {GenerateNoteCategory.SELECTION_GAP: 1},
    "resources/questionnaires/program_rules.py": {GenerateNoteCategory.FORM_STRUCTURE: 1},
    "resources/questionnaires/schemas.py": {GenerateNoteCategory.SELECTION_GAP: 1},
    "service.py": {
        GenerateNoteCategory.BUILD_COST: 1,
        GenerateNoteCategory.COMPILE_REMOVED: 1,
        GenerateNoteCategory.EMPTY_SELECTION: 4,
        GenerateNoteCategory.FORM_STRUCTURE: 2,
        GenerateNoteCategory.INSTANCE_DATA_GAP: 3,
        GenerateNoteCategory.REFUSED_FORM: 1,
        GenerateNoteCategory.SELECTION_CLOSURE: 1,
        GenerateNoteCategory.SCAFFOLD_DRIFT: 1,
        GenerateNoteCategory.SELECTION_MISMATCH: 3,
    },
}

#: Which kinds only restate what `d2w fhir validate` reports, spelled out rather than derived.
#:
#: The module owns the split as one frozenset; this table repeats the verdict per kind so a category
#: moved across the line has to be moved here too, in the file that documents what the line means.
_ECHO_VERDICTS: dict[GenerateNoteCategory, bool] = {
    GenerateNoteCategory.SELECTION_MISMATCH: False,
    GenerateNoteCategory.SELECTION_CLOSURE: False,
    GenerateNoteCategory.EMPTY_SELECTION: False,
    GenerateNoteCategory.SELECTION_GAP: False,
    GenerateNoteCategory.REFUSED_FORM: False,
    GenerateNoteCategory.FORM_STRUCTURE: False,
    GenerateNoteCategory.SKIPPED_QUESTION: False,
    GenerateNoteCategory.ANSWER_FALLBACK: False,
    GenerateNoteCategory.INSTANCE_DATA_GAP: False,
    GenerateNoteCategory.BUILD_COST: False,
    GenerateNoteCategory.COMPILE_REMOVED: False,
    GenerateNoteCategory.SCAFFOLD_DRIFT: False,
    GenerateNoteCategory.NAME_SUBSTITUTION: False,
    GenerateNoteCategory.CODE_SUBSTITUTION: False,
    GenerateNoteCategory.CODE_FALLBACK: True,
    GenerateNoteCategory.CODE_COLLISION: True,
    GenerateNoteCategory.STEM_FALLBACK: True,
}


def _modules() -> list[Path]:
    """Every source file that deals in generate notes, in a stable order.

    A module qualifies by importing `dhis2w_fhir.notes`, which is what raising a generate note takes.
    Other note-shaped things in the package - a conversion carries its own - are a different surface
    with a different model, and the taxonomy this file guards is the generate one.
    """
    return sorted(
        path
        for path in _PACKAGE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and (path.name == "notes.py" or "dhis2w_fhir.notes import" in path.read_text(encoding="utf-8"))
    )


def _observed_inventory() -> dict[str, dict[GenerateNoteCategory, int]]:
    """Read every note site out of the package's own syntax tree, by module and kind."""
    inventory: dict[str, dict[GenerateNoteCategory, int]] = {}
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in _NOTE_CONSTRUCTORS:
                continue
            argument = node.args[0]
            assert isinstance(argument, ast.Attribute), f"{path}: a note kind is a GenerateNoteCategory member"
            category = GenerateNoteCategory[argument.attr]
            module = str(path.relative_to(_PACKAGE_ROOT))
            inventory.setdefault(module, {})
            inventory[module][category] = inventory[module].get(category, 0) + 1
    return inventory


def _appended_notes() -> list[tuple[str, ast.expr]]:
    """Every expression the package appends to a note list, with the module that appends it."""
    appended: list[tuple[str, ast.expr]] = []
    for path in _modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "append":
                continue
            target = node.func.value
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            if name.endswith("notes"):
                appended.append((str(path.relative_to(_PACKAGE_ROOT)), node.args[0]))
    return appended


def test_the_emission_inventory_is_the_recorded_taxonomy() -> None:
    """Every note the package raises is one of the recorded kinds, raised where the inventory says."""
    assert _observed_inventory() == _EMISSION_INVENTORY


@pytest.mark.parametrize("category", list(GenerateNoteCategory))
def test_every_category_has_at_least_one_emission_site(category: GenerateNoteCategory) -> None:
    """A kind nothing raises is a kind nobody classified against - the taxonomy describes real notes."""
    raised = {kind for kinds in _EMISSION_INVENTORY.values() for kind in kinds}
    assert category in raised


def test_no_note_is_appended_as_a_bare_string() -> None:
    """A note enters a report through its constructor, so nothing can slip in as untyped text."""
    for module, argument in _appended_notes():
        assert isinstance(argument, ast.Call), f"{module}: a note is built by a constructor, not by an expression"
        assert isinstance(argument.func, ast.Name), f"{module}: a note is built by a constructor"
        assert argument.func.id in _NOTE_CONSTRUCTORS, f"{module}: {argument.func.id} does not carry a note kind"


def test_the_message_builder_is_only_ever_reached_through_a_constructor() -> None:
    """`aggregate_note` formats text and nothing more, so only `notes.py` calls it directly."""
    callers = {
        str(path.relative_to(_PACKAGE_ROOT))
        for path in _modules()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "aggregate_note"
    }
    assert callers == {"notes.py"}


@pytest.mark.parametrize("category", list(GenerateNoteCategory))
def test_the_validate_echo_split_is_the_recorded_one(category: GenerateNoteCategory) -> None:
    """Which kinds restate a validate finding is a decision, so it is spelled out kind by kind."""
    note = GenerateNote(category=category, message="anything")
    assert note.echoes_validate is _ECHO_VERDICTS[category]
    assert (category in VALIDATE_ECHO_CATEGORIES) is _ECHO_VERDICTS[category]


def test_a_note_serialises_as_its_kind_its_text_and_the_echo_verdict() -> None:
    """The `--json` payload is the whole model: a consumer reads the kind, not the prose."""
    note = generate_note(GenerateNoteCategory.CODE_FALLBACK, "1 option has no code")
    assert note.model_dump() == {
        "category": GenerateNoteCategory.CODE_FALLBACK,
        "message": "1 option has no code",
        "echoes_validate": True,
    }
    assert note.model_dump(mode="json")["category"] == "code-fallback"


def test_an_aggregate_note_carries_the_message_the_string_builder_wrote() -> None:
    """The wrapper adds a kind and changes not one character of the text a run prints."""
    subjects = [f"Unit {index}" for index in range(7)]
    headline = "7 organisation units have malformed geometry"
    note = aggregate_generate_note(GenerateNoteCategory.INSTANCE_DATA_GAP, headline, subjects)
    assert note.message == aggregate_note(headline, subjects)
    assert note.message.endswith("Unit 0, Unit 1, Unit 2, Unit 3, Unit 4 and 2 more")


def test_a_note_renders_as_its_message() -> None:
    """A note stands in for the string it replaced wherever something formats it."""
    assert str(generate_note(GenerateNoteCategory.BUILD_COST, "the registry is large")) == "the registry is large"
