"""Introspect generated models to describe a type's schema — offline, version-bound.

"Schema" here is the toolkit's own typed view of a type: the OpenAPI-derived `oas`
tree (preferred — the maturing source of truth) with the `/api/schemas`-derived
`schemas` tree as the interim complement. Both are introspected from the generated
trees for the active plugin version; no DHIS2 connection is made.
"""

from __future__ import annotations

import difflib
import importlib
import types
import typing

from pydantic import BaseModel

from dhis2w_core.v41.plugins.schema.models import SchemaField, TypeSchema

#: Active version key ("v41" / "v42" / "v43"), derived from this module's import path so the
#: file is identical across the three plugin trees and always reads its matching generated tree.
_VERSION = __name__.split(".")[1]


def describe_type(name: str, source: str = "auto") -> TypeSchema | None:
    """Return the schema of `name` from the preferred generated tree, or None if unknown."""
    for tree in _sources(source):
        index = _model_index(_load(tree))
        by_lower = {key.lower(): key for key in index}
        for variant in _singular_variants(name):
            canonical = by_lower.get(variant.lower())
            if canonical is not None:
                return _describe(index[canonical], canonical, tree)
    return None


def search_types(query: str, *, limit: int = 8) -> list[str]:
    """Return close-match type names across both trees for a 'did you mean' hint."""
    names = sorted(set(_model_index(_load("oas"))) | set(_model_index(_load("schemas"))))
    lowered = query.lower()
    ordered: dict[str, None] = {}
    for candidate in [n for n in names if lowered in n.lower()]:
        ordered.setdefault(candidate, None)
    for candidate in difflib.get_close_matches(query, names, n=limit, cutoff=0.6):
        ordered.setdefault(candidate, None)
    return list(ordered)[:limit]


def _describe(model: type[BaseModel], canonical: str, tree: str) -> TypeSchema:
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
    return TypeSchema(name=canonical, source=tree, version=_VERSION, field_count=len(fields), fields=fields)


def _load(tree: str) -> object:
    """Import a generated subpackage (`oas` / `schemas`) for the active version."""
    return importlib.import_module(f"dhis2w_client.generated.{_VERSION}.{tree}")


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
        return getattr(annotation, "__name__", str(annotation).replace("typing.", ""))
    args = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        parts = [_render_type(arg) for arg in args if arg is not type(None)]
        rendered = " | ".join(parts)
        return rendered + (" | None" if type(None) in args else "")
    name = getattr(origin, "__name__", str(origin))
    return f"{name}[{', '.join(_render_type(arg) for arg in args)}]"
