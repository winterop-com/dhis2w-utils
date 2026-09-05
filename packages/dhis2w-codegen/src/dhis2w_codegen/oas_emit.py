"""Emit pydantic models from a DHIS2 `/api/openapi.json` `components/schemas` section.

Complements `emit.py` (which derives from `/api/schemas`). OpenAPI covers the
instance-side shapes that `/api/schemas` doesn't describe — tracker writes,
WebMessage envelopes, discriminated auth schemes, aggregate data values, etc.

The two emitters deliberately share only the generic helpers in `_shared.py`.
The intermediate models differ: `/api/schemas` has DHIS2-specific property
metadata (owner, collection, itemPropertyType) that OpenAPI lacks, and OpenAPI
has generic JSON-schema primitives (oneOf, $ref, inline nested objects) that
`/api/schemas` doesn't emit.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jinja2 import Environment
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_codegen._shared import (
    build_template_environment,
    format_output,
    python_string_literal,
    sanitize_identifier,
)
from dhis2w_codegen.names import to_class_name, to_module_name
from dhis2w_codegen.spec_patches import apply_patches

# OpenAPI schema names that collide with Python builtins. Pydantic resolves
# `list[Warning]` to the builtin `Warning` class at FieldInfo construction
# regardless of `defer_build` — so renaming at emit time is the only reliable
# fix. Keep the wire name intact via model_config alias / docstring; only the
# Python class identifier changes.
_BUILTIN_SHADOWS = {name: f"DHIS2{name}" for name in dir(builtins)}

# Fields where the OpenAPI shape is unergonomic (undiscriminated oneOf with many
# branches) — override to `dict[str, Any]`. The hand-written models on top of
# these use typed accessor methods to project the field into a useful shape.
_FIELD_OVERRIDES: dict[tuple[str, str], str] = {
    ("WebMessage", "response"): "dict[str, Any]",
}

# Wire names that collide with pydantic's BaseModel API. Rename with a trailing
# underscore + alias on the field. `sanitize_identifier` already handles Python
# keywords (`from`, `class`) via the same pattern — this adds the pydantic-
# reserved set on top.
_PYDANTIC_RESERVED = {
    "schema",
    "copy",
    "dict",
    "json",
    "parse_obj",
    "parse_raw",
    "validate",
    "construct",
    "model_config",
    "model_fields",
    "model_extra",
}

# Enums with more values than this threshold are treated as open-ended strings
# rather than closed StrEnums. DHIS2's `ErrorCode` lists 450+ members and adds
# new ones in every minor release; emitting it as a strict enum would reject
# every unknown code that lands between regen passes. Keeping the small
# enums (status, domain, value-type, ...) as proper StrEnums preserves IDE
# completion where the set is genuinely closed.
_MAX_CLOSED_ENUM_SIZE = 64


class OasEmitResult(BaseModel):
    """Summary of what the OpenAPI emitter wrote for a single version."""

    model_config = ConfigDict(frozen=True)

    version_key: str
    raw_version: str
    components_total: int
    components_emitted: int
    enums_count: int
    aliases_count: int
    objects_count: int
    manifest_path: Path


class _OasField(BaseModel):
    """One pydantic field rendered into an OAS-derived model template."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: str
    required: bool
    alias: str | None = None
    description: str = ""
    # Discriminator-tag fields: when the type is a single-value `Literal[...]`,
    # emit with the tag as the default value (required + default) so pydantic
    # can route a discriminated union without callers repeating the tag.
    literal_default: str | None = None


class _OasClass(BaseModel):
    """One rendered OAS-derived pydantic model."""

    model_config = ConfigDict(frozen=True)

    class_name: str
    module_name: str
    docstring: str
    fields: list[_OasField]
    imports_enums: list[str] = Field(default_factory=list)  # names in `_enums`
    imports_aliases: list[str] = Field(default_factory=list)  # names in `_aliases`
    imports_siblings: list[tuple[str, str]] = Field(default_factory=list)  # (module_name, class_name)
    imports_typing_any: bool = False
    imports_datetime: bool = False
    imports_typing_annotated: bool = False
    imports_typing_literal: bool = False
    imports_pydantic_field: bool = False


class _OasEnumValue(BaseModel):
    """One entry in a generated OAS StrEnum."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    value: str
    # Python source for the value, escaped via `repr` so quotes, backslashes,
    # newlines and non-ASCII text in a wire value cannot break the emitted file.
    literal: str


class _OasEnum(BaseModel):
    """One OAS-derived StrEnum."""

    model_config = ConfigDict(frozen=True)

    class_name: str
    description: str = ""
    values: list[_OasEnumValue]


class _OasAlias(BaseModel):
    """A scalar type alias (e.g. `UID_DataElement` -> `str`)."""

    model_config = ConfigDict(frozen=True)

    name: str
    target: str
    description: str = ""


def emit_from_openapi(openapi_path: Path, output_dir: Path, *, version_key: str, raw_version: str) -> OasEmitResult:
    """Emit the OAS-derived modules for `version_key` at `output_dir/oas/`.

    Input is the committed `openapi.json`; no network required. Output is
    deterministic: the same OpenAPI input produces byte-identical files on
    every run (after `ruff format`).
    """
    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    components: dict[str, dict[str, Any]] = spec.get("components", {}).get("schemas", {})

    # Patch the spec for known upstream DHIS2 gaps (missing discriminators,
    # variant schemas without Jackson `type` tags, etc.). See
    # `dhis2w_codegen.spec_patches` for the full list + per-patch BUGS.md refs.
    applied_patches = apply_patches(components)
    for patch in applied_patches:
        print(f"  spec-patch applied: {patch.name} ({patch.bugs_ref})")

    oas_dir = output_dir / "oas"
    oas_dir.mkdir(parents=True, exist_ok=True)

    enums, aliases, classes = _build(components)

    environment = _template_env()
    _write_aliases(oas_dir, environment, aliases)
    _write_enums(oas_dir, environment, enums)
    _write_classes(oas_dir, environment, classes)
    _write_init(oas_dir, environment, enums, aliases, classes)

    manifest_path = _write_manifest(
        output_dir=output_dir,
        openapi_path=openapi_path,
        version_key=version_key,
        raw_version=raw_version,
        components=components,
        enums=enums,
        aliases=aliases,
        classes=classes,
    )

    format_output(oas_dir)

    return OasEmitResult(
        version_key=version_key,
        raw_version=raw_version,
        components_total=len(components),
        components_emitted=len(enums) + len(aliases) + len(classes),
        enums_count=len(enums),
        aliases_count=len(aliases),
        objects_count=len(classes),
        manifest_path=manifest_path,
    )


# ---------------------------------------------------------------------------
# Parsing / classification
# ---------------------------------------------------------------------------


def _build(components: dict[str, dict[str, Any]]) -> tuple[list[_OasEnum], list[_OasAlias], list[_OasClass]]:
    """Classify every component schema and build the emission intermediate forms."""
    enums: dict[str, _OasEnum] = {}
    aliases: dict[str, _OasAlias] = {}
    inline_children: dict[str, list[_OasClass]] = defaultdict(list)  # parent module → child classes
    classes_by_name: dict[str, _OasClass] = {}

    # First pass: classify enums + aliases so the second pass can resolve $refs.
    for name, schema in components.items():
        if _is_enum(schema):
            enums[name] = _build_enum(name, schema)
        elif _is_alias(schema):
            aliases[name] = _build_alias(name, schema)

    # Second pass: build object classes. Inline nested objects get synthesised
    # sibling classes in the parent's module; they're collected per-parent and
    # rendered in the same file.
    for name, schema in components.items():
        if name in enums or name in aliases:
            continue
        if not _is_object(schema):
            # Schemas we don't yet emit: bare oneOf at the top level (e.g.
            # `Instant` would fall here if it weren't classified as an alias),
            # unexpected shapes. Skip silently — manifest records that they
            # were not emitted.
            continue
        built = _build_class(name, schema, enums=enums, aliases=aliases, inline_bag=inline_children)
        classes_by_name[name] = built

    # Flatten: inline children first (so parent annotations resolve against
    # already-defined names), then the parent class.
    ordered: list[_OasClass] = []
    for name in sorted(classes_by_name.keys()):
        parent = classes_by_name[name]
        if parent.module_name in inline_children:
            ordered.extend(
                sorted(inline_children[parent.module_name], key=lambda c: c.class_name),
            )
        ordered.append(parent)

    return (
        sorted(enums.values(), key=lambda e: e.class_name),
        sorted(aliases.values(), key=lambda a: a.name),
        ordered,
    )


def _is_enum(schema: dict[str, Any]) -> bool:
    """True when the schema defines a pure enum (`type: string` + `enum: [...]`).

    Very large enums (above `_MAX_CLOSED_ENUM_SIZE` members) are treated as
    open-ended string aliases instead — DHIS2's `ErrorCode` grows across
    releases, so a closed enum would reject every new code.
    """
    if "enum" not in schema or schema.get("type") not in {"string", "integer"}:
        return False
    return len(schema.get("enum", [])) <= _MAX_CLOSED_ENUM_SIZE


def _is_alias(schema: dict[str, Any]) -> bool:
    """True when the schema is a primitive wrapper with no nested properties.

    Catches UID_* wrappers, Instant, bare `{type: string}` / `{oneOf: [...]}`,
    and large enums that `_is_enum` rejected as open-ended (they become
    plain `str` / `int` aliases at the field site).
    """
    if "properties" in schema:
        return False
    if "oneOf" in schema:
        return True
    return schema.get("type") in {"string", "integer", "number", "boolean", "any"}


def _is_object(schema: dict[str, Any]) -> bool:
    """True when the schema has `properties` (with or without `type: object`)."""
    return "properties" in schema


def _safe_class_name(name: str) -> str:
    """Return `to_class_name(name)` with builtin shadows renamed (e.g. Warning -> DHIS2Warning)."""
    base = to_class_name(name)
    return _BUILTIN_SHADOWS.get(base, base)


def _build_enum(name: str, schema: dict[str, Any]) -> _OasEnum:
    """Build the intermediate form for a StrEnum."""
    raw_values = schema.get("enum", [])
    return _OasEnum(
        class_name=_safe_class_name(name),
        description=(schema.get("description") or "").strip().splitlines()[0] if schema.get("description") else "",
        values=[_build_enum_value(v) for v in raw_values],
    )


def _build_enum_value(raw: Any) -> _OasEnumValue:
    """Normalise one enum member into a Python-safe identifier + wire value."""
    raw_str = str(raw)
    identifier = re.sub(r"[^A-Za-z0-9_]", "_", raw_str).upper()
    if not identifier or not (identifier[0].isalpha() or identifier[0] == "_"):
        identifier = f"_{identifier}"
    return _OasEnumValue(identifier=identifier, value=raw_str, literal=python_string_literal(raw_str))


def _build_alias(name: str, schema: dict[str, Any]) -> _OasAlias:
    """Build the intermediate form for a scalar alias (UID_*, Instant, etc.)."""
    target = _scalar_expr(schema)
    description = (schema.get("description") or "").strip().splitlines()[0] if schema.get("description") else ""
    return _OasAlias(name=_safe_class_name(name), target=target, description=description)


def _scalar_expr(schema: dict[str, Any]) -> str:
    """Resolve a primitive/oneOf schema into a Python type expression."""
    if "oneOf" in schema:
        parts = [_scalar_expr(branch) for branch in schema["oneOf"]]
        # Dedupe while preserving order; `str | int` not `str | int | str`.
        deduped: list[str] = []
        for part in parts:
            if part not in deduped:
                deduped.append(part)
        return " | ".join(deduped)
    type_keyword = schema.get("type")
    fmt = schema.get("format")
    if type_keyword == "string" and fmt == "date-time":
        return "datetime"
    if type_keyword == "string":
        return "str"
    if type_keyword == "integer":
        return "int"
    if type_keyword == "number":
        return "float"
    if type_keyword == "boolean":
        return "bool"
    if type_keyword == "any":
        return "Any"
    return "Any"


def _build_class(
    name: str,
    schema: dict[str, Any],
    *,
    enums: dict[str, _OasEnum],
    aliases: dict[str, _OasAlias],
    inline_bag: dict[str, list[_OasClass]],
    override_module_name: str | None = None,
) -> _OasClass:
    """Build the intermediate form for an object schema.

    `override_module_name` lets inline child classes share their parent's
    module file instead of getting a separate file — otherwise the synthesised
    `<Parent><Property>` class gets its own module and the parent's import
    silently breaks.
    """
    class_name = _safe_class_name(name)
    module_name = override_module_name or to_module_name(name)
    description = (schema.get("description") or "").strip().splitlines()[0] if schema.get("description") else ""
    if description and description[-1] not in ".!?":
        # ruff D415 requires terminal punctuation on docstrings; the OpenAPI
        # `description` field doesn't always include one (especially on v41).
        description = f"{description}."
    docstring = description or f"OpenAPI schema `{name}`."

    # OpenAPI's `required:` list is intentionally ignored at the field level —
    # DHIS2's spec over-marks fields as required relative to what real
    # responses actually contain (e.g. `WebMessage.errorCode` is marked
    # required but 200-OK responses omit it). Fields emit as optional.
    #
    # Exception: single-value `Literal[...]` fields — Jackson discriminator
    # tags added by `spec_patches`. Those emit as required-with-default so
    # pydantic can route discriminated unions. The special-case lands
    # downstream in the loop below via `_single_literal_value`.
    fields: list[_OasField] = []
    imports_enums: set[str] = set()
    imports_aliases: set[str] = set()
    imports_siblings: set[tuple[str, str]] = set()
    needs_any = False
    needs_datetime = False
    needs_annotated = False
    needs_literal = False
    needs_pydantic_field = False

    for wire_name, prop_schema in sorted(schema.get("properties", {}).items()):
        type_expr, field_imports = _resolve_type(
            prop_schema,
            enums=enums,
            aliases=aliases,
            parent_class=class_name,
            parent_module=module_name,
            property_name=wire_name,
            inline_bag=inline_bag,
        )
        override = _FIELD_OVERRIDES.get((name, wire_name))
        if override is not None:
            type_expr = override
            # Discard imports collected while resolving the original schema —
            # the override expression replaces the type, so any siblings /
            # aliases / enums referenced by the discarded branches are no
            # longer needed in this module.
            field_imports = _ResolvedImports()
            if "Any" in override:
                field_imports.typing_any = True
        python_name, alias = sanitize_identifier(wire_name)
        if python_name == wire_name and wire_name in _PYDANTIC_RESERVED:
            python_name = f"{wire_name}_"
            alias = wire_name
        if not python_name.isidentifier() or python_name[0].isdigit() or python_name.startswith("_"):
            sanitized = re.sub(r"[^A-Za-z0-9_]", "_", python_name).lstrip("_")
            if not sanitized or sanitized[0].isdigit():
                sanitized = f"field_{sanitized}"
            python_name = sanitized
            alias = wire_name
        imports_enums.update(field_imports.enums)
        imports_aliases.update(field_imports.aliases)
        imports_siblings.update((m, c) for (m, c) in field_imports.siblings if m != module_name)
        needs_any = needs_any or field_imports.typing_any
        needs_datetime = needs_datetime or field_imports.datetime_
        needs_annotated = needs_annotated or field_imports.typing_annotated
        needs_literal = needs_literal or field_imports.typing_literal
        needs_pydantic_field = needs_pydantic_field or field_imports.pydantic_field
        # Single-value Literal fields (emitted for Jackson-style discriminator
        # tags) become required-with-default so pydantic can route discriminated
        # unions and callers don't have to pass the tag themselves.
        literal_default = _single_literal_value(type_expr)
        field_is_required = literal_default is not None
        description = (
            (prop_schema.get("description") or "").strip().splitlines()[0]
            if isinstance(prop_schema, dict) and prop_schema.get("description")
            else ""
        )
        # Mirror the template's `_Field(...)` emission rule: required-with-
        # literal-default uses `_Field` only when an alias is also present;
        # other fields use `_Field` whenever alias or description is set.
        field_uses_field_call = bool(alias) if literal_default else bool(alias) or bool(description)
        needs_pydantic_field = needs_pydantic_field or field_uses_field_call
        fields.append(
            _OasField(
                name=python_name,
                type=type_expr,
                required=field_is_required,
                alias=alias,
                description=description,
                literal_default=literal_default,
            )
        )

    return _OasClass(
        class_name=class_name,
        module_name=module_name,
        docstring=docstring,
        fields=fields,
        imports_enums=sorted(imports_enums),
        imports_aliases=sorted(imports_aliases),
        imports_siblings=sorted(imports_siblings),
        imports_typing_any=needs_any,
        imports_datetime=needs_datetime,
        imports_typing_annotated=needs_annotated,
        imports_typing_literal=needs_literal,
        imports_pydantic_field=needs_pydantic_field,
    )


class _ResolvedImports(BaseModel):
    """Imports required for a single field's rendered type expression."""

    enums: set[str] = Field(default_factory=set)
    aliases: set[str] = Field(default_factory=set)
    siblings: set[tuple[str, str]] = Field(default_factory=set)  # (module_name, class_name)
    typing_any: bool = False
    datetime_: bool = False
    typing_annotated: bool = False
    typing_literal: bool = False
    pydantic_field: bool = False

    model_config = ConfigDict(frozen=False)


def _resolve_type(
    schema: Any,
    *,
    enums: dict[str, _OasEnum],
    aliases: dict[str, _OasAlias],
    parent_class: str,
    parent_module: str,
    property_name: str,
    inline_bag: dict[str, list[_OasClass]],
    depth: int = 0,
) -> tuple[str, _ResolvedImports]:
    """Resolve a property schema into `(python_type_expr, imports)`.

    Handles `$ref`, primitives, arrays, inline nested objects (synthesised as
    sibling classes named `<Parent><Property>` in the parent's module), enums,
    `oneOf`, `additionalProperties` maps, and a safety fallback of
    `dict[str, Any]` past depth=2 on inline objects to keep the generator
    terminating on unexpected shapes.
    """
    imports = _ResolvedImports()
    if not isinstance(schema, dict):
        imports.typing_any = True
        return "Any", imports

    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        if ref_name in enums:
            class_name = enums[ref_name].class_name
            imports.enums.add(class_name)
            return class_name, imports
        if ref_name in aliases:
            alias = aliases[ref_name]
            if alias.target == "str":
                # UID_* wrappers flatten to plain `str` at the field level —
                # no import needed. The alias is still emitted as a module
                # symbol for documentation + future callers.
                return "str", imports
            imports.aliases.add(alias.name)
            return alias.name, imports
        # Fall through: $ref to a sibling class.
        class_name = _safe_class_name(ref_name)
        module_name = to_module_name(ref_name)
        if module_name != parent_module:
            imports.siblings.add((module_name, class_name))
        return class_name, imports

    if "oneOf" in schema:
        branches: list[str] = []
        for branch in schema["oneOf"]:
            expr, branch_imports = _resolve_type(
                branch,
                enums=enums,
                aliases=aliases,
                parent_class=parent_class,
                parent_module=parent_module,
                property_name=property_name,
                inline_bag=inline_bag,
                depth=depth + 1,
            )
            branches.append(expr)
            imports.enums.update(branch_imports.enums)
            imports.aliases.update(branch_imports.aliases)
            imports.siblings.update(branch_imports.siblings)
            imports.typing_any = imports.typing_any or branch_imports.typing_any
            imports.datetime_ = imports.datetime_ or branch_imports.datetime_
            imports.typing_literal = imports.typing_literal or branch_imports.typing_literal
        deduped: list[str] = []
        for part in branches:
            if part not in deduped:
                deduped.append(part)
        union_expr = " | ".join(deduped) if deduped else "Any"
        discriminator = schema.get("discriminator")
        if isinstance(discriminator, dict) and isinstance(discriminator.get("propertyName"), str) and deduped:
            # Tagged union — emit as Annotated[Union, _Field(discriminator="prop")] so
            # pydantic routes validation / serialisation via the discriminator field.
            # `_Field` matches the template's `from pydantic import Field as _Field` alias.
            imports.typing_annotated = True
            imports.pydantic_field = True
            property_literal = discriminator["propertyName"]
            return f"Annotated[{union_expr}, _Field(discriminator={python_string_literal(property_literal)})]", imports
        return union_expr, imports

    if "enum" in schema and schema.get("type") in {"string", "integer"}:
        values = schema.get("enum") or []
        # Inline enum: emit `Literal[...]` so the closed value set survives into the
        # static type. Single-value enums are typically Jackson tags on discriminated
        # unions; multi-value enums show up on v41 fields whose v42 counterparts use
        # a named `$ref` component (v41 inlines the same data instead of factoring
        # it out). Cap the Literal size so mypy stays responsive on pathological
        # cases like `ErrorReport.errorCode` which carries 460+ values; past the
        # cap, fall back to plain `str`/`int`.
        if (
            isinstance(values, list)
            and values
            and all(isinstance(v, (str, int)) for v in values)
            and len(values) <= _MAX_CLOSED_ENUM_SIZE
        ):
            imports.typing_literal = True
            rendered = [python_string_literal(value) if isinstance(value, str) else str(value) for value in values]
            return f"Literal[{', '.join(rendered)}]", imports
        return "str" if schema.get("type") == "string" else "int", imports

    type_keyword = schema.get("type")
    fmt = schema.get("format")

    if type_keyword == "array":
        inner, inner_imports = _resolve_type(
            schema.get("items") or {},
            enums=enums,
            aliases=aliases,
            parent_class=parent_class,
            parent_module=parent_module,
            property_name=property_name,
            inline_bag=inline_bag,
            depth=depth + 1,
        )
        imports.enums.update(inner_imports.enums)
        imports.aliases.update(inner_imports.aliases)
        imports.siblings.update(inner_imports.siblings)
        imports.typing_any = imports.typing_any or inner_imports.typing_any
        imports.datetime_ = imports.datetime_ or inner_imports.datetime_
        imports.typing_literal = imports.typing_literal or inner_imports.typing_literal
        return f"list[{inner}]", imports

    if type_keyword == "object":
        if "properties" in schema:
            if depth >= 2:
                imports.typing_any = True
                return "dict[str, Any]", imports
            child_name = f"{parent_class}{to_class_name(property_name)}"
            child_class = _build_class(
                # Synthesise a pseudo-schema name for the inline object and
                # pin it to the parent's module so both land in the same file.
                child_name,
                schema,
                enums=enums,
                aliases=aliases,
                inline_bag=inline_bag,
                override_module_name=parent_module,
            )
            inline_bag[parent_module].append(child_class)
            return child_name, imports
        additional = schema.get("additionalProperties")
        if additional is True or additional is None:
            imports.typing_any = True
            return "dict[str, Any]", imports
        value_expr, value_imports = _resolve_type(
            additional,
            enums=enums,
            aliases=aliases,
            parent_class=parent_class,
            parent_module=parent_module,
            property_name=property_name,
            inline_bag=inline_bag,
            depth=depth + 1,
        )
        imports.enums.update(value_imports.enums)
        imports.aliases.update(value_imports.aliases)
        imports.siblings.update(value_imports.siblings)
        imports.typing_any = imports.typing_any or value_imports.typing_any
        imports.datetime_ = imports.datetime_ or value_imports.datetime_
        imports.typing_literal = imports.typing_literal or value_imports.typing_literal
        return f"dict[str, {value_expr}]", imports

    # Primitives.
    if type_keyword == "string" and fmt == "date-time":
        imports.datetime_ = True
        return "datetime", imports
    if type_keyword == "string":
        return "str", imports
    if type_keyword == "integer":
        return "int", imports
    if type_keyword == "number":
        return "float", imports
    if type_keyword == "boolean":
        return "bool", imports
    if type_keyword == "any":
        imports.typing_any = True
        return "Any", imports

    imports.typing_any = True
    return "Any", imports


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


_SINGLE_LITERAL_RE = re.compile(r"""^Literal\[('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|\d+)\]$""")


def _single_literal_value(type_expr: str) -> str | None:
    """If `type_expr` is exactly a single-value `Literal[...]`, return that value's source; else None."""
    match = _SINGLE_LITERAL_RE.match(type_expr)
    return match.group(1) if match else None


def _template_env() -> Environment:
    """Build the Jinja environment used by every OAS template."""
    return build_template_environment()


def _write_aliases(oas_dir: Path, environment: Environment, aliases: Iterable[_OasAlias]) -> None:
    """Render `_aliases.py` with every scalar type alias."""
    alias_list = list(aliases)
    needs_datetime = any("datetime" in a.target for a in alias_list)
    needs_any = any("Any" in a.target for a in alias_list)
    content = environment.get_template("oas/oas_aliases.py.jinja").render(
        aliases=alias_list,
        needs_datetime=needs_datetime,
        needs_any=needs_any,
    )
    (oas_dir / "_aliases.py").write_text(content, encoding="utf-8")


def _write_enums(oas_dir: Path, environment: Environment, enums: Iterable[_OasEnum]) -> None:
    """Render `_enums.py` with every StrEnum derived from the OpenAPI spec."""
    content = environment.get_template("oas/oas_enums.py.jinja").render(enums=list(enums))
    (oas_dir / "_enums.py").write_text(content, encoding="utf-8")


def _write_classes(oas_dir: Path, environment: Environment, classes: Iterable[_OasClass]) -> None:
    """Render one `<module>.py` per parent class (inline children co-located)."""
    # Group by module so inline-child classes join their parent.
    by_module: dict[str, list[_OasClass]] = defaultdict(list)
    for cls in classes:
        by_module[cls.module_name].append(cls)
    template = environment.get_template("oas/oas_model.py.jinja")
    for module_name, module_classes in by_module.items():
        # Merge imports across all classes in the module so the file has one
        # import block at the top.
        merged_enums = sorted({e for c in module_classes for e in c.imports_enums})
        merged_aliases = sorted({a for c in module_classes for a in c.imports_aliases})
        merged_siblings = sorted(
            {(m, cn) for c in module_classes for (m, cn) in c.imports_siblings if m != module_name},
        )
        needs_any = any(c.imports_typing_any for c in module_classes)
        needs_datetime = any(c.imports_datetime for c in module_classes)
        needs_annotated = any(c.imports_typing_annotated for c in module_classes)
        needs_literal = any(c.imports_typing_literal for c in module_classes)
        needs_pydantic_field = any(c.imports_pydantic_field for c in module_classes)
        content = template.render(
            classes=module_classes,
            imports_enums=merged_enums,
            imports_aliases=merged_aliases,
            imports_siblings=merged_siblings,
            imports_typing_any=needs_any,
            imports_datetime=needs_datetime,
            imports_typing_annotated=needs_annotated,
            imports_typing_literal=needs_literal,
            imports_pydantic_field=needs_pydantic_field,
        )
        (oas_dir / f"{module_name}.py").write_text(content, encoding="utf-8")


def _write_init(
    oas_dir: Path,
    environment: Environment,
    enums: Iterable[_OasEnum],
    aliases: Iterable[_OasAlias],
    classes: Iterable[_OasClass],
) -> None:
    """Render `oas/__init__.py` with a flat re-export of every emitted symbol."""
    enum_names = [e.class_name for e in enums]
    alias_names = [a.name for a in aliases if a.target != "str"]  # UID_* aliases flatten; don't export
    class_pairs = [(c.module_name, c.class_name) for c in classes]
    # Deduplicate module names at emission time — multiple classes often
    # share a source module (e.g. `aggregate_data_exchange_params` ships
    # three `*Params*` siblings), and the `_submodule_names` set would
    # otherwise carry duplicate literals. Python's set collapses them at
    # runtime, but the rendered text would still include duplicates that
    # trip `ruff B033`.
    submodule_names = sorted({module_name for module_name, _ in class_pairs})
    content = environment.get_template("oas/oas_init.py.jinja").render(
        enum_names=enum_names,
        alias_names=alias_names,
        class_pairs=class_pairs,
        submodule_names=submodule_names,
        all_names=sorted({*enum_names, *alias_names, *[cn for _, cn in class_pairs]}),
    )
    (oas_dir / "__init__.py").write_text(content, encoding="utf-8")


def _write_manifest(
    *,
    output_dir: Path,
    openapi_path: Path,
    version_key: str,
    raw_version: str,
    components: dict[str, Any],
    enums: Iterable[_OasEnum],
    aliases: Iterable[_OasAlias],
    classes: Iterable[_OasClass],
) -> Path:
    """Write an `openapi_manifest.json` summary so review diffs stay readable.

    Records the OpenAPI file's hash + the sorted list of emitted component
    names so a rebuild that produces the same output is a no-op in git.
    Wall-clock timestamps are deliberately omitted — `openapi_sha256` is
    the stable identifier for "what spec did we generate from".
    """
    sorted_keys = sorted(components.keys())
    digest = hashlib.sha256(openapi_path.read_bytes()).hexdigest()
    manifest = {
        "version_key": version_key,
        "raw_version": raw_version,
        "openapi_sha256": digest,
        "components_total": len(components),
        "emitted": {
            "enums": [e.class_name for e in enums],
            "aliases": [a.name for a in aliases],
            "classes": [c.class_name for c in classes],
        },
        "components_sorted": sorted_keys,
    }
    path = output_dir / "openapi_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
