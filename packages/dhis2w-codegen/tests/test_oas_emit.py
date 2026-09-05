"""Unit tests for the OpenAPI emitter — feeds in minimal specs and inspects output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dhis2w_codegen.oas_emit import _build_enum, _template_env, emit_from_openapi


def _run_emitter(tmp_path: Path, spec: dict[str, Any]) -> Path:
    """Write `spec` to disk and run the emitter against it."""
    openapi_path = tmp_path / "openapi.json"
    openapi_path.write_text(json.dumps(spec), encoding="utf-8")
    emit_from_openapi(openapi_path, tmp_path, version_key="vtest", raw_version="2.42.0")
    return tmp_path / "oas"


def test_emitter_produces_importable_module(tmp_path: Path) -> None:
    """Emitted `oas/` module imports cleanly and exposes one pydantic class per schema."""
    spec = {
        "components": {
            "schemas": {
                "Color": {
                    "type": "string",
                    "enum": ["RED", "GREEN", "BLUE"],
                },
                "Point": {
                    "type": "object",
                    "required": ["x"],
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "colour": {"$ref": "#/components/schemas/Color"},
                    },
                },
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib

        if "oas" in sys.modules:
            del sys.modules["oas"]
        module = importlib.import_module("oas")
        assert hasattr(module, "Color"), "enum not re-exported"
        assert hasattr(module, "Point"), "object not re-exported"
        point_cls = module.Point
        instance = point_cls.model_validate({"x": 1, "y": 2, "colour": "RED"})
        assert instance.x == 1
        assert instance.colour == module.Color.RED
    finally:
        sys.path.remove(str(tmp_path))
    assert (oas_dir / "_enums.py").exists()
    assert (oas_dir / "point.py").exists()


def test_emitter_renames_builtin_shadows(tmp_path: Path) -> None:
    """`Warning` (Python builtin) becomes `DHIS2Warning` so pydantic doesn't clash."""
    spec = {
        "components": {
            "schemas": {
                "Warning": {
                    "type": "object",
                    "properties": {"msg": {"type": "string"}},
                },
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    init_src = (oas_dir / "__init__.py").read_text()
    assert "DHIS2Warning" in init_src
    assert "from .warning import Warning" not in init_src


def test_emitter_flattens_uid_aliases(tmp_path: Path) -> None:
    """UID_* wrappers flatten to plain `str` at field sites (no import needed)."""
    spec = {
        "components": {
            "schemas": {
                "UID_Thing": {
                    "type": "string",
                    "pattern": "^[a-z]{11}$",
                    "maxLength": 11,
                    "minLength": 11,
                },
                "HasThing": {
                    "type": "object",
                    "properties": {
                        "ref": {"$ref": "#/components/schemas/UID_Thing"},
                    },
                },
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    model_src = (oas_dir / "has_thing.py").read_text()
    assert "ref: str | None" in model_src


def test_emitter_writes_manifest(tmp_path: Path) -> None:
    """`openapi_manifest.json` summarises what was emitted for deterministic review."""
    spec = {"components": {"schemas": {"One": {"type": "object", "properties": {"n": {"type": "integer"}}}}}}
    _run_emitter(tmp_path, spec)
    manifest = json.loads((tmp_path / "openapi_manifest.json").read_text())
    assert manifest["version_key"] == "vtest"
    assert "One" in manifest["emitted"]["classes"]
    assert "openapi_sha256" in manifest


def test_emitter_lifts_inline_string_enum_to_literal(tmp_path: Path) -> None:
    """Multi-value inline `enum` on a string field becomes `Literal[...]`, not bare `str`.

    DHIS2 v41's OpenAPI inlines closed enums on every field instead of factoring
    them out as named components like v42/v43. Emitting `str | None` for those
    drops the closed-set info — `Literal[...]` keeps it.
    """
    spec = {
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["A", "B", "C"]},
                        "kinds": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["X", "Y"]},
                        },
                    },
                },
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    model_src = (oas_dir / "item.py").read_text()
    assert "from typing import Literal" in model_src, "Literal import missing"
    assert '"A", "B", "C"' in model_src, "scalar inline enum not lifted to Literal"
    assert '"X", "Y"' in model_src, "array-of-inline-enum not lifted (typing_literal not propagated through array)"


def test_emitter_inline_enum_over_size_cap_falls_back_to_str(tmp_path: Path) -> None:
    """Inline enums above `_MAX_CLOSED_ENUM_SIZE` (64) degrade to plain `str` to keep mypy responsive."""
    big_enum = [f"V{i}" for i in range(100)]
    spec = {
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "properties": {"code": {"type": "string", "enum": big_enum}},
                }
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    model_src = (oas_dir / "item.py").read_text()
    assert "code: str | None" in model_src
    assert "Literal" not in model_src


def test_emitter_does_not_emit_unused_imports(tmp_path: Path) -> None:
    """Modules without siblings, _Field calls, or typing helpers don't get those imports."""
    spec = {
        "components": {
            "schemas": {
                "Plain": {
                    "type": "object",
                    "properties": {
                        "flag": {"type": "boolean"},
                        "count": {"type": "integer"},
                    },
                },
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    src = (oas_dir / "plain.py").read_text()
    assert "TYPE_CHECKING" not in src, "TYPE_CHECKING imported into a module with no siblings"
    assert "_Field" not in src, "_Field imported into a module that uses no alias / description / discriminator"
    assert "Annotated" not in src, "Annotated imported into a module with no discriminated unions"
    assert "Literal" not in src, "Literal imported into a module with no single-value enum tags"


def test_emitter_is_regen_stable(tmp_path: Path) -> None:
    """A second run against the same spec produces byte-identical output (no spurious drift)."""
    spec = {
        "components": {
            "schemas": {
                "Color": {"type": "string", "enum": ["RED", "GREEN", "BLUE"]},
                "Point": {
                    "type": "object",
                    "required": ["x"],
                    "properties": {
                        "x": {"type": "number", "description": "X coordinate"},
                        "y": {"type": "number"},
                        "colour": {"$ref": "#/components/schemas/Color"},
                    },
                },
                "Box": {
                    "type": "object",
                    "properties": {
                        "tl": {"$ref": "#/components/schemas/Point"},
                        "br": {"$ref": "#/components/schemas/Point"},
                    },
                },
            }
        }
    }
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    first_oas = _run_emitter(first_path, spec)
    second_oas = _run_emitter(second_path, spec)
    first_files = sorted(p.name for p in first_oas.iterdir() if p.is_file())
    second_files = sorted(p.name for p in second_oas.iterdir() if p.is_file())
    assert first_files == second_files
    for filename in first_files:
        if filename == "openapi_manifest.json":
            continue  # Manifest carries a generated_at timestamp — exclude.
        first_text = (first_oas / filename).read_text()
        second_text = (second_oas / filename).read_text()
        assert first_text == second_text, f"emitter output drifted across runs in {filename}"


HOSTILE_ENUM_VALUES = [
    'say "hello"',
    "back\\slash",
    "line\nbreak",
    "café — naïve",
]


def _compile_rendered_source(source: str, filename: str) -> dict[str, Any]:
    """Compile rendered template source in memory and return its module namespace."""
    namespace: dict[str, Any] = {}
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102
    return namespace


def test_oas_enum_values_with_hostile_characters_round_trip() -> None:
    """Quotes, backslashes, newlines and non-ASCII enum values compile and read back verbatim."""
    enum_model = _build_enum("Hostile", {"type": "string", "enum": HOSTILE_ENUM_VALUES})
    source = _template_env().get_template("oas/oas_enums.py.jinja").render(enums=[enum_model])
    namespace = _compile_rendered_source(source, "<oas_enums>")
    rendered_enum = namespace["Hostile"]
    assert [member.value for member in rendered_enum] == HOSTILE_ENUM_VALUES


def test_oas_enum_description_with_hostile_characters_compiles() -> None:
    """A description carrying a backslash and a trailing quote stays inside the generated docstring."""
    enum_model = _build_enum(
        "Described",
        {"type": "string", "enum": ["ONE"], "description": 'ends with a backslash \\ and a quote "'},
    )
    source = _template_env().get_template("oas/oas_enums.py.jinja").render(enums=[enum_model])
    namespace = _compile_rendered_source(source, "<oas_enums>")
    assert namespace["Described"].ONE.value == "ONE"


def test_oas_inline_literal_with_hostile_characters_compiles(tmp_path: Path) -> None:
    """An inline field enum carrying a double quote emits a compilable `Literal[...]`."""
    spec = {
        "components": {
            "schemas": {
                "Tagged": {
                    "type": "object",
                    "properties": {"kind": {"type": "string", "enum": ['say "hello"', "plain"]}},
                }
            }
        }
    }
    oas_dir = _run_emitter(tmp_path, spec)
    source = (oas_dir / "tagged.py").read_text(encoding="utf-8")
    compile(source, "<tagged>", "exec")
