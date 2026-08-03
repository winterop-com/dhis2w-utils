"""Emit pydantic schemas + resource classes + init stub from a SchemasManifest."""

from __future__ import annotations

import json
import keyword
import re
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict

from dhis2w_codegen._shared import format_output
from dhis2w_codegen.discover import Schema, SchemaProperty, SchemasManifest
from dhis2w_codegen.mapping import python_type_for
from dhis2w_codegen.names import to_class_name, to_module_name


class _Field(BaseModel):
    """One pydantic field rendered into the model template."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: str
    docstring: str = ""
    alias: str | None = None  # wire name when the Python attribute had to rename (keyword collision)


class _Resource(BaseModel):
    """One resource rendered into the resources template."""

    model_config = ConfigDict(frozen=True)

    class_name: str
    module_name: str
    plural: str
    attr_name: str


class _ClassDoc(BaseModel):
    """Components of a generated class's docstring."""

    model_config = ConfigDict(frozen=True)

    summary: str  # one-liner at the top of the docstring
    endpoint: str | None = None  # /api/<endpoint> for the collection
    persisted: bool = True
    metadata: bool = False


_HAND_WRITTEN_ENUMS: dict[str, str] = {
    # DHIS2 Java class -> enum class name re-exported from generated/v{N}/enums.py.
    "org.hisp.dhis.period.PeriodType": "PeriodType",
}


class _EnumValue(BaseModel):
    """One entry in a generated StrEnum."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    value: str


class _Enum(BaseModel):
    """One generated StrEnum class derived from a CONSTANT property's klass."""

    model_config = ConfigDict(frozen=True)

    class_name: str
    klass: str
    values: list[_EnumValue]


def emit(manifest: SchemasManifest, output_dir: Path) -> None:
    """Emit the generated v{NN} module at `output_dir` based on `manifest`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas_dir = output_dir / "schemas"
    schemas_dir.mkdir(exist_ok=True)

    environment = Environment(
        loader=PackageLoader("dhis2w_codegen", "templates"),
        autoescape=select_autoescape(default=False),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        # trim/lstrip so `{% if %}` control tags don't leave blank lines
        # in the rendered output — essential for deterministic rebuilds.
        trim_blocks=True,
        lstrip_blocks=True,
    )

    manifest_path = output_dir / "schemas_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (output_dir / "common.py").write_text(
        environment.get_template("common.py.jinja").render(version_key=manifest.version_key),
        encoding="utf-8",
    )
    enum_by_klass = _collect_enums(manifest.schemas)
    (output_dir / "enums.py").write_text(
        environment.get_template("enums.py.jinja").render(
            version_key=manifest.version_key,
            enums=sorted(enum_by_klass.values(), key=lambda e: e.class_name),
        ),
        encoding="utf-8",
    )

    resources: list[_Resource] = []
    all_schemas: list[tuple[str, str]] = []  # (module_name, class_name) for every emitted pydantic schema
    model_template = environment.get_template("model.py.jinja")

    # Pre-pass: build a klass -> (class_name, module_name) registry so
    # collections of COMPLEX sub-objects (DataSet.dataSetElements, etc.) can
    # emit a typed `list[DataSetElement]` instead of `list[Any]`.
    complex_classes: dict[str, tuple[str, str]] = {}
    for schema in manifest.schemas:
        if not schema.plural or not schema.klass:
            continue
        identifier = _identifier_for(schema)
        if identifier:
            complex_classes[schema.klass] = (to_class_name(identifier), to_module_name(identifier))

    seen_classes: set[str] = set()
    seen_attrs: set[str] = set()
    for schema in manifest.schemas:
        # Generate a pydantic model for every persisted schema that has a name,
        # even non-metadata ones (DataSetElement, AttributeValue, ...). Only
        # schemas that live at their own `/api/<plural>` endpoint get a
        # Resources accessor — that's what `metadata=True` marks.
        if not schema.plural:
            continue
        identifier = _identifier_for(schema)
        if not identifier:
            continue
        class_name = to_class_name(identifier)
        module_name = to_module_name(identifier)
        if class_name in seen_classes:
            continue
        seen_classes.add(class_name)
        attr_name = to_module_name(schema.plural)
        if attr_name in seen_attrs:
            continue
        seen_attrs.add(attr_name)
        fields = _fields_for(schema, enum_by_klass, complex_classes, skip_class=schema.klass)
        class_doc = _class_doc_for(schema, manifest.version_key)
        used_enum_names: set[str] = set()
        for prop in schema.properties:
            if prop.klass and prop.klass in enum_by_klass:
                used_enum_names.add(enum_by_klass[prop.klass].class_name)
            elif prop.klass and prop.klass in _HAND_WRITTEN_ENUMS:
                used_enum_names.add(_HAND_WRITTEN_ENUMS[prop.klass])
        used_enums = sorted(used_enum_names)
        # Typed imports for collections of COMPLEX sub-objects (DataSetElement, ...).
        complex_imports: list[tuple[str, str]] = []
        seen_imports: set[str] = set()
        for prop in schema.properties:
            if not (prop.collection and prop.itemPropertyType == "COMPLEX" and prop.itemKlass):
                continue
            if prop.itemKlass == schema.klass:
                continue  # self-reference; skip to avoid circular imports
            entry = complex_classes.get(prop.itemKlass)
            if not entry:
                continue
            cls_name, mod_name = entry
            if cls_name in seen_imports:
                continue
            seen_imports.add(cls_name)
            complex_imports.append((mod_name, cls_name))
        complex_imports.sort()

        # Track which optional imports the rendered module actually needs so
        # the template only emits in-use names. Substring match is safe — the
        # Reference / datetime / Any tokens never collide with generated class
        # names. `Field` is used whenever a field has alias or docstring, and
        # the `Field(description=...)` mention in the class docstring also
        # references it lexically (the template emits that line unconditionally).
        field_types_joined = " ".join(f.type for f in fields)
        needs_datetime = "datetime" in field_types_joined
        needs_any = "Any" in field_types_joined
        needs_reference = "Reference" in field_types_joined
        needs_field = any(f.alias or f.docstring for f in fields)

        (schemas_dir / f"{module_name}.py").write_text(
            model_template.render(
                class_name=class_name,
                version_key=manifest.version_key,
                fields=fields,
                class_doc=class_doc,
                used_enums=used_enums,
                complex_imports=complex_imports,
                needs_datetime=needs_datetime,
                needs_any=needs_any,
                needs_reference=needs_reference,
                needs_field=needs_field,
            ),
            encoding="utf-8",
        )
        all_schemas.append((module_name, class_name))
        # Only metadata schemas live at `/api/<plural>` — others (DataSetElement,
        # AttributeValue, ...) are inline on their parent and don't get a
        # Resources accessor. Models for them are still emitted.
        if schema.metadata:
            resources.append(
                _Resource(
                    class_name=class_name,
                    module_name=module_name,
                    plural=schema.plural,
                    attr_name=attr_name,
                )
            )

    resources.sort(key=lambda r: r.class_name)

    (output_dir / "resources.py").write_text(
        environment.get_template("resources.py.jinja").render(
            version_key=manifest.version_key,
            resources=resources,
        ),
        encoding="utf-8",
    )
    resource_classes = [r.class_name for r in resources]
    (output_dir / "__init__.py").write_text(
        environment.get_template("init.py.jinja").render(
            version_key=manifest.version_key,
            raw_version=manifest.raw_version,
            resource_classes=resource_classes,
        ),
        encoding="utf-8",
    )
    # Re-export every pydantic schema from schemas/__init__.py so
    # `from dhis2w_client.generated.v{N}.schemas import DataElement` works
    # alongside the top-level `from dhis2w_client.generated.v{N} import DataElement`.
    # "schemas" mirrors DHIS2's own `/api/schemas` endpoint and frees up
    # "models" for SQLAlchemy-style DB models elsewhere in the workspace.
    all_schemas.sort(key=lambda pair: pair[1])
    schemas_init_lines: list[str] = [
        f'"""Generated DHIS2 {manifest.version_key} pydantic schemas."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    for module_name, class_name in all_schemas:
        schemas_init_lines.append(f"from .{module_name} import {class_name}")
    schemas_init_lines.extend(
        [
            "",
            "__all__ = [",
            *[f'    "{class_name}",' for _, class_name in all_schemas],
            "]",
            "",
        ]
    )
    (schemas_dir / "__init__.py").write_text("\n".join(schemas_init_lines), encoding="utf-8")

    format_output(output_dir)


def _identifier_for(schema: Schema) -> str | None:
    """Derive a unique identifier for the schema (Java class tail, singular, or name)."""
    if schema.klass:
        tail = schema.klass.rsplit(".", 1)[-1]
        if tail:
            return tail
    if schema.singular:
        return schema.singular
    return schema.name or None


def _class_doc_for(schema: Schema, version_key: str) -> _ClassDoc:
    """Summarise a schema into the pieces the class docstring template needs."""
    label = schema.displayName or schema.singular or schema.name
    kind = "persisted metadata" if schema.persisted and schema.metadata else "DHIS2 resource"
    summary = f"DHIS2 {label} - {kind} (generated from /api/schemas at DHIS2 {version_key})."
    # DHIS2's apiEndpoint is an absolute URL pinned to whatever instance we
    # discovered against — `http://localhost:8080/api/dataElements` for a
    # root-hosted dev stack, `https://play.im.dhis2.org/dev-2-43/api/dataElements`
    # for the public play instance with a context path. Drop everything before
    # `/api/` so the docstring records the version-portable relative path.
    endpoint = schema.apiEndpoint
    if endpoint and endpoint.startswith(("http://", "https://")):
        marker = endpoint.find("/api/")
        endpoint = endpoint[marker:] if marker != -1 else None
    return _ClassDoc(
        summary=summary,
        endpoint=endpoint,
        persisted=schema.persisted,
        metadata=schema.metadata,
    )


def _field_description(prop: SchemaProperty) -> str:
    """Build a short description for a field, highlighting owner/writability/bounds."""
    parts: list[str] = []
    if prop.collection:
        target = (prop.itemKlass or prop.klass or "").rsplit(".", 1)[-1]
        if target:
            parts.append(f"Collection of {target}.")
    elif prop.klass and not prop.simple:
        target = prop.klass.rsplit(".", 1)[-1]
        if target:
            parts.append(f"Reference to {target}.")
    # DHIS2-specific: non-owner collections + references are the inverse side of
    # an association, and writes against them are silently ignored by the API.
    # ASCII only — the generator emits these into docstrings rendered via
    # `|tojson`, which would escape a fancy em-dash to `\u2014` (6 chars) and
    # push several already-long lines past the 120-col limit.
    if not prop.owner and (prop.collection or (prop.klass is not None and not prop.simple)):
        parts.append("Read-only (inverse side).")
    elif not prop.writable:
        parts.append("Read-only.")
    if prop.unique:
        parts.append("Unique.")
    bounds: list[str] = []
    # DHIS2 uses Double.MIN_VALUE / MAX_VALUE as "unbounded" sentinels; filter those
    # so docstrings don't leak `max=1.7976931348623157e+308` (unreadable) or `min=0`
    # (always-implied "non-negative", adds noise not signal).
    if prop.min is not None and prop.min > 0:
        bounds.append(f"min={int(prop.min) if float(prop.min).is_integer() else prop.min}")
    if prop.max is not None and prop.max < 1e18:
        bounds.append(f"max={int(prop.max) if float(prop.max).is_integer() else prop.max}")
    if bounds:
        parts.append("Length/value " + ", ".join(bounds) + ".")
    return " ".join(parts)


def _fields_for(
    schema: Schema,
    enum_by_klass: dict[str, _Enum],
    complex_classes: dict[str, tuple[str, str]] | None = None,
    *,
    skip_class: str | None = None,
) -> list[_Field]:
    """Build the pydantic field list for a single schema.

    DHIS2's OpenAPI / /api/schemas names the primary key `uid` on every
    metadata resource, but the actual REST API wire format uses `id` on
    reads and writes (the `uid` spelling rejects with 409 on POST). We
    rename at emit time so generated models match the wire format and
    callers can do `Model(id=...).model_dump()` without gymnastics.

    CONSTANT properties resolve to a generated `StrEnum` class name from
    `enum_by_klass` so callers get `DataElement(domainType=DataElementDomain.AGGREGATE)`
    instead of stringly-typed `Literal[...]` options.
    """
    seen: set[str] = set()
    fields: list[_Field] = []
    for property_spec in schema.properties:
        wire_name = _wire_name_for(property_spec)
        if not wire_name or wire_name in seen:
            continue
        if not wire_name.isidentifier():
            continue
        python_name = wire_name
        alias: str | None = None
        if keyword.iskeyword(wire_name):
            # DHIS2 ships field names that collide with Python keywords
            # (e.g. Relationship.from). Pydantic lets us keep the wire name
            # via Field(alias=...) while using a safe Python identifier.
            python_name = f"{wire_name}_"
            alias = wire_name
        seen.add(wire_name)
        enum_name: str | None = None
        if property_spec.propertyType == "CONSTANT" and property_spec.klass in enum_by_klass:
            enum_name = enum_by_klass[property_spec.klass].class_name
        elif property_spec.klass in _HAND_WRITTEN_ENUMS:
            # DHIS2's schema marks these as TEXT because upstream uses a class
            # hierarchy (e.g. PeriodType) instead of a real enum, but the valid
            # values are a known stable set — we ship them as hand-written
            # StrEnums in dhis2w_client and re-export them from the generated
            # enums module.
            enum_name = _HAND_WRITTEN_ENUMS[property_spec.klass]
        if enum_name and not property_spec.collection:
            field_type = enum_name
        elif enum_name and property_spec.collection:
            field_type = f"list[{enum_name}]"
        elif (
            property_spec.collection
            and property_spec.itemPropertyType == "COMPLEX"
            and property_spec.itemKlass
            and property_spec.itemKlass != skip_class
            and complex_classes
            and property_spec.itemKlass in complex_classes
        ):
            # Collection of COMPLEX sub-objects (DataSetElement, AttributeValue) —
            # use the generated model class name instead of `list[Any]`.
            class_name, _ = complex_classes[property_spec.itemKlass]
            field_type = f"list[{class_name}]"
        else:
            field_type = python_type_for(property_spec.model_dump())
        fields.append(
            _Field(
                name=python_name,
                type=field_type,
                docstring=_field_description(property_spec),
                alias=alias,
            )
        )
    fields.sort(key=lambda f: f.name)
    return fields


def _wire_name_for(prop: SchemaProperty) -> str:
    """Resolve the JSON field name DHIS2 actually uses on the wire.

    `/api/schemas` reports two candidate names per property:
      - `name`       the Java getter-derived singular (`organisationUnit`).
      - `fieldName`  the Hibernate column name or the JSON plural, depending
                     on the property. For `dataSetElement` it's the correct
                     JSON plural `dataSetElements`; for `organisationUnit`
                     on DataSet it's `sources` — a Hibernate alias that
                     does NOT match the wire format (which is `organisationUnits`).

    For collections DHIS2's JSON wire key is usually the regular English plural
    of `name` — `dataElementGroup` -> `dataElementGroups`, `authority` ->
    `authorities`. Trust `fieldName` whenever it looks like a regular plural
    (`name + "s"`, `name + "es"`, or `name[:-1] + "ies"`); fall back to the
    naive `name + "s"` when `fieldName` is an unrelated Hibernate alias like
    `sources`.

    For scalars `name` is the JSON wire key; `fieldName` is the Hibernate
    column or Java field name and only matches the wire shape when they
    happen to coincide. Prefer `name`, fall back to `fieldName` when
    `name` is missing. Covers the primary key (`name=id, fieldName=uid`),
    `OrganisationUnit.level/hierarchyLevel`, `CategoryOption.isDefault/default`,
    and the `repetition/eventRepetition` family.
    """
    name = prop.name or prop.fieldName or ""
    if prop.collection and name:
        if prop.fieldName and prop.fieldName in {
            name + "s",
            name + "es",
            name[:-1] + "ies" if name.endswith("y") else "",
        }:
            wire = prop.fieldName
        elif not name.endswith("s"):
            wire = name + "s"
        else:
            wire = name
    else:
        wire = prop.name or prop.fieldName or ""
    if wire == "uid":
        wire = "id"
    return wire


def _collect_enums(schemas: list[Schema]) -> dict[str, _Enum]:
    """Build the global per-version enum registry keyed by fully-qualified Java klass.

    Walks every CONSTANT-typed property across every schema, dedupes by klass,
    and synthesises a Python StrEnum class name from the klass's last segment
    (collision-resolved by prefixing the penultimate package segment).
    """
    registry: dict[str, _Enum] = {}
    claimed_names: dict[str, str] = {}  # class_name -> klass (for collision detection)
    # First pass: assign the preferred (tail-segment) name when unique.
    for schema in schemas:
        for prop in schema.properties:
            if prop.propertyType != "CONSTANT" or not prop.klass or not prop.constants:
                continue
            if prop.klass in registry:
                continue
            tail = prop.klass.rsplit(".", 1)[-1]
            tail_class = to_class_name(tail)
            if tail_class in claimed_names and claimed_names[tail_class] != prop.klass:
                # Collision — qualify by the immediate package, e.g. MappingEventStatus.
                segments = prop.klass.split(".")
                prefix = to_class_name(segments[-2]) if len(segments) >= 2 else ""
                tail_class = f"{prefix}{to_class_name(tail)}"
            claimed_names[tail_class] = prop.klass
            registry[prop.klass] = _Enum(
                class_name=tail_class,
                klass=prop.klass,
                values=[_enum_value(c) for c in prop.constants],
            )
    return registry


def _enum_value(raw: str) -> _EnumValue:
    """Turn a DHIS2 constant (e.g. `LAST_5_YEARS`, `2xx`) into a valid Python attribute name."""
    identifier = re.sub(r"[^A-Za-z0-9_]", "_", raw).upper()
    if not identifier or not (identifier[0].isalpha() or identifier[0] == "_"):
        identifier = f"_{identifier}"
    if keyword.iskeyword(identifier.lower()):
        identifier = f"{identifier}_"
    return _EnumValue(identifier=identifier, value=raw)
