"""Describe a type's schema by introspecting the generated models for the server's version.

"Schema" is the toolkit's own typed view of a type: the OpenAPI-derived `oas` tree (preferred —
the maturing source of truth) with the `/api/schemas`-derived `schemas` tree as the interim
complement. The DHIS2 major is auto-detected from the live server (`/api/system/info`, which is
SNAPSHOT-safe), then the matching generated tree is introspected — there is no per-type wire fetch.
"""

from __future__ import annotations

import difflib
import enum
import importlib
import types
import typing

from pydantic import BaseModel

from dhis2w_core.profile import Profile
from dhis2w_core.v43.client_context import open_client
from dhis2w_core.v43.plugins.schema.models import SchemaField, TypeSchema


async def detect_version(profile: Profile) -> str:
    """Return the server's generated-client version key (e.g. "v41"), auto-detected on connect."""
    async with open_client(profile) as client:
        return client.version_key


def describe_type(version: str, name: str, source: str = "auto") -> TypeSchema | None:
    """Return the schema of `name` from the given version's preferred generated tree, or None."""
    for tree in _sources(source):
        index = _index(version, tree)
        by_lower = {key.lower(): key for key in index}
        for variant in _singular_variants(name):
            canonical = by_lower.get(variant.lower())
            if canonical is not None:
                return _describe(index[canonical], canonical, tree, version)
    return None


def search_types(version: str, query: str, *, limit: int = 8) -> list[str]:
    """Return close-match type names across every tree of `version` for a 'did you mean' hint."""
    names = sorted(set(_index(version, "oas")) | set(_index(version, "schemas")))
    lowered = query.lower()
    ordered: dict[str, None] = {}
    for candidate in [name for name in names if lowered in name.lower()]:
        ordered.setdefault(candidate, None)
    for candidate in difflib.get_close_matches(query, names, n=limit, cutoff=0.6):
        ordered.setdefault(candidate, None)
    return list(ordered)[:limit]


def unknown_fields(version: str, name: str, fields: str) -> list[str]:
    """Return requested bare field names absent from every generated model for `name`.

    Conservative: only plain comma-lists of simple identifiers are checked. Returns `[]`
    when the `--fields` expression uses non-trivial syntax (presets like `:all`, wildcards,
    `!exclusions`, nested `a[b,c]`, dotted `a.b`) or when the type is unknown — so a real
    expression never produces a false warning. Membership unions the oas + schemas + tracker
    trees, so a field is flagged only when no generated view knows it (a likely typo).
    """
    tokens = [token.strip() for token in fields.split(",") if token.strip()]
    if not tokens or any(_has_field_syntax(token) for token in tokens):
        return []
    known = _known_field_names(version, name)
    if known is None:
        return []
    lowered = {field.lower() for field in known}
    return [token for token in tokens if token.lower() not in lowered]


def _has_field_syntax(token: str) -> bool:
    """Return True if a `--fields` token uses preset/wildcard/exclusion/nested/dotted syntax."""
    return any(char in token for char in ":*![].")


def _known_field_names(version: str, name: str) -> set[str] | None:
    """Union of declared field names for `name` across the generated trees, or None if unknown."""
    found: set[str] = set()
    for tree in ("oas", "schemas"):
        index = _index(version, tree)
        by_lower = {key.lower(): key for key in index}
        for variant in _singular_variants(name):
            canonical = by_lower.get(variant.lower())
            if canonical is not None:
                found |= set(index[canonical].model_fields)
                break
    return found or None


def _describe(model: type[BaseModel], canonical: str, tree: str, version: str) -> TypeSchema:
    """Build a `TypeSchema` from a generated model's declared fields."""
    fields = [
        SchemaField(
            name=field_name,
            type=_render_type(info.annotation),
            required=info.is_required(),
            description=info.description,
        )
        for field_name, info in model.model_fields.items()
    ]
    return TypeSchema(name=canonical, source=tree, version=version, field_count=len(fields), fields=fields)


def _index(version: str, tree: str) -> dict[str, type[BaseModel]]:
    """Build the merged model index for a logical tree.

    The `oas` tree also folds in the generated `tracker` module (TrackerEvent,
    TrackerTrackedEntity, …) — those are OpenAPI-derived instance-side write shapes that
    live in their own module but belong to the same OAS-preferred view.
    """
    modules = ("oas", "tracker") if tree == "oas" else (tree,)
    merged: dict[str, type[BaseModel]] = {}
    for module in modules:
        merged.update(_model_index(_load(version, module)))
    return merged


def _load(version: str, tree: str) -> object:
    """Import a generated subpackage/module (`oas` / `schemas` / `tracker`) for the given version."""
    return importlib.import_module(f"dhis2w_client.generated.{version}.{tree}")


def _model_index(module: object) -> dict[str, type[BaseModel]]:
    """Map every BaseModel class exported by a generated subpackage to its class name."""
    index: dict[str, type[BaseModel]] = {}
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            index[attr] = obj
    return index


def _sources(source: str) -> tuple[str, ...]:
    """Resolve the `--source` selector to an ordered tuple of tree names (oas preferred)."""
    if source == "oas":
        return ("oas",)
    if source == "schemas":
        return ("schemas",)
    return ("oas", "schemas")


def _singular_variants(name: str) -> list[str]:
    """Yield singular candidates for a plural wire name (e.g. dataElements -> dataElement)."""
    variants = [name]
    if name.endswith("ies"):
        variants.append(name[:-3] + "y")
    if name.endswith("es"):
        variants.append(name[:-2])
    if name.endswith("s"):
        variants.append(name[:-1])
    return variants


def _render_type(annotation: object) -> str:
    """Render a field annotation as a readable type string (forward refs, unions, generics)."""
    if annotation is None:
        return "Any"
    if isinstance(annotation, typing.ForwardRef):
        return annotation.__forward_arg__
    if isinstance(annotation, str):
        return annotation
    origin = typing.get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return _render_enum(annotation)
        return getattr(annotation, "__name__", str(annotation).replace("typing.", ""))
    args = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        parts = [_render_type(arg) for arg in args if arg is not type(None)]
        rendered = " | ".join(parts)
        return rendered + (" | None" if type(None) in args else "")
    name = getattr(origin, "__name__", str(origin))
    return f"{name}[{', '.join(_render_type(arg) for arg in args)}]"


def _render_enum(enum_cls: type[enum.Enum]) -> str:
    """Render an enum field as `Name (VAL1, VAL2, ...)` so a model sees the allowed values."""
    values = ", ".join(str(member.value) for member in enum_cls)
    return f"{enum_cls.__name__} ({values})"
