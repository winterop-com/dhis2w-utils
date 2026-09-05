"""Unit tests for the /api/schemas emitter — feeds in synthetic manifests and inspects output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dhis2w_codegen._shared import build_template_environment
from dhis2w_codegen.discover import Schema, SchemaProperty, SchemasManifest
from dhis2w_codegen.emit import _Enum, _enum_value, emit


def _manifest_with(schemas: list[Schema]) -> SchemasManifest:
    """Build a minimal manifest wrapping the provided schemas."""
    return SchemasManifest(raw_version="2.42.0", version_key="vtest", schemas=schemas)


def test_emitter_omits_unused_imports_for_simple_schema(tmp_path: Path) -> None:
    """A schema whose fields are all primitive str/bool/int doesn't import datetime / Any / Reference / Field."""
    plain = Schema(
        name="plain",
        plural="plains",
        singular="plain",
        klass="org.example.Plain",
        metadata=True,
        properties=[
            SchemaProperty(name="flag", propertyType="BOOLEAN"),
            SchemaProperty(name="count", propertyType="INTEGER"),
            SchemaProperty(name="label", propertyType="TEXT"),
        ],
    )
    emit(_manifest_with([plain]), tmp_path)
    src = (tmp_path / "schemas" / "plain.py").read_text()
    assert "datetime" not in src, "datetime imported into a module without datetime fields"
    assert "from typing import Any" not in src, "Any imported into a module without Any-typed fields"
    assert "from ..common import Reference" not in src, "Reference imported into a module without Reference fields"
    assert ", Field" not in src, "Field imported into a module where every field is plain T | None = None"


def test_emitter_includes_imports_when_needed(tmp_path: Path) -> None:
    """A schema referencing dates / Reference / docstring metadata pulls in only the imports it actually uses."""
    rich = Schema(
        name="rich",
        plural="riches",
        singular="rich",
        klass="org.example.Rich",
        metadata=True,
        properties=[
            SchemaProperty(name="created", propertyType="DATETIME"),
            SchemaProperty(name="parent", propertyType="REFERENCE", klass="org.example.Plain"),
            SchemaProperty(name="extra", propertyType="COMPLEX", klass="org.example.Anonymous", min=1.0, max=10.0),
        ],
    )
    emit(_manifest_with([rich]), tmp_path)
    src = (tmp_path / "schemas" / "rich.py").read_text()
    assert "from datetime import datetime" in src
    assert "from typing import Any" in src  # COMPLEX falls back to Any
    assert "from ..common import Reference" in src
    assert "Field(" in src  # bounds + docstring metadata trip Field()


def test_emitter_is_regen_stable(tmp_path: Path) -> None:
    """A second `emit()` against the same manifest produces byte-identical output."""
    schemas = [
        Schema(
            name="plain",
            plural="plains",
            singular="plain",
            klass="org.example.Plain",
            metadata=True,
            properties=[
                SchemaProperty(name="flag", propertyType="BOOLEAN"),
                SchemaProperty(name="when", propertyType="DATETIME"),
            ],
        ),
        Schema(
            name="rich",
            plural="riches",
            singular="rich",
            klass="org.example.Rich",
            metadata=True,
            properties=[
                SchemaProperty(name="ref", propertyType="REFERENCE", klass="org.example.Plain"),
            ],
        ),
    ]
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    emit(_manifest_with(schemas), first)
    emit(_manifest_with(schemas), second)
    first_files = sorted(p.relative_to(first).as_posix() for p in first.rglob("*.py"))
    second_files = sorted(p.relative_to(second).as_posix() for p in second.rglob("*.py"))
    assert first_files == second_files
    for relative in first_files:
        first_text = (first / relative).read_text()
        second_text = (second / relative).read_text()
        assert first_text == second_text, f"emitter output drifted across runs in {relative}"


HOSTILE_CONSTANTS = [
    'say "hello"',
    "back\\slash",
    "line\nbreak",
    "café — naïve",
]


def test_schema_enum_values_with_hostile_characters_round_trip() -> None:
    """Quotes, backslashes, newlines and non-ASCII constants compile and read back verbatim."""
    enum_model = _Enum(
        class_name="Hostile",
        klass="org.example.Hostile",
        values=[_enum_value(constant) for constant in HOSTILE_CONSTANTS],
    )
    source = (
        build_template_environment()
        .get_template("enums.py.jinja")
        .render(
            version_key="v42",
            enums=[enum_model],
        )
    )
    namespace: dict[str, Any] = {}
    exec(compile(source, "<enums>", "exec"), namespace)  # noqa: S102
    assert [member.value for member in namespace["Hostile"]] == HOSTILE_CONSTANTS


def test_schema_enum_klass_with_hostile_characters_compiles() -> None:
    """A Java class name carrying a backslash stays inside the generated docstring."""
    enum_model = _Enum(
        class_name="Described",
        klass="org.example.Odd\\Name",
        values=[_enum_value("ONE")],
    )
    source = (
        build_template_environment()
        .get_template("enums.py.jinja")
        .render(
            version_key="v42",
            enums=[enum_model],
        )
    )
    namespace: dict[str, Any] = {}
    exec(compile(source, "<enums>", "exec"), namespace)  # noqa: S102
    assert namespace["Described"].ONE.value == "ONE"
