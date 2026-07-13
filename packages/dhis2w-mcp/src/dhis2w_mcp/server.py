"""FastMCP server entry for dhis2w-mcp — mounts plugins from dhis2w-core."""

from __future__ import annotations

import typing

from dhis2w_core.plugin import discover_plugins, resolve_startup_version
from dhis2w_core.profile import bind_version_tree
from fastmcp import FastMCP
from fastmcp.tools.base import Tool
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from dhis2w_mcp.profile_errors import NoProfileHintMiddleware
from dhis2w_mcp.readonly import ReadOnlyMiddleware, is_read_tool, readonly_enabled


def build_server() -> FastMCP:
    """Create the FastMCP instance with every discovered plugin registered.

    Pins the resolved startup version on `dhis2w_core.profile._BOUND_VERSION_KEY`
    so that per-call profiles which pin a different DHIS2 major raise
    `ProfileVersionMismatchError` from `resolve_profile()` rather than silently
    parsing wire payloads through the wrong schemas. The CLI does not need this
    binding because it discovers plugins fresh per invocation.
    """
    server = FastMCP(name="dhis2")
    bound_tree = resolve_startup_version()
    bind_version_tree(bound_tree)
    for plugin in discover_plugins(bound_tree):
        plugin.register_mcp(server)
    _eager_rebuild_tool_return_types(server)
    _annotate_read_only_hints(server)
    server.add_middleware(NoProfileHintMiddleware())
    if readonly_enabled():
        server.add_middleware(ReadOnlyMiddleware())
    return server


def main() -> None:
    """Console-script entrypoint: build the server and run it over stdio."""
    build_server().run()


def _eager_rebuild_tool_return_types(server: FastMCP) -> None:
    """Resolve forward refs on every pydantic class reachable from a tool return type.

    Pydantic v2 lazily builds `__pydantic_validator__` on first
    `model_validate`, but `__pydantic_serializer__` stays as `MockValSer`
    until `model_rebuild()` runs explicitly. FastMCP serializes tool
    returns directly through the model serializer (no prior validation
    happens on the path), so any class declared with `defer_build=True`
    raises `'MockValSer' object is not an instance of 'SchemaSerializer'`.

    Every OAS-emitted pydantic class uses `defer_build=True` to keep
    `d2w --help` startup fast (skipping the eager rebuild loop saves
    ~900 ms of CLI boot time). MCP server boot is the right place to
    pay that cost — this server is long-lived, the rebuild happens once,
    and skipping it leaves tool returns silently broken.

    Walks every registered tool's return-type annotation and calls
    `model_rebuild()` on every pydantic class encountered (including
    inside `list[X]`, `dict[..., X]`, `X | Y` unions, and similar
    generics). Reads from `server.providers[*]._components` so this
    runs synchronously even when `build_server()` is called inside an
    async context (in-process MCP integration tests + examples).
    """
    seen: set[type[BaseModel]] = set()

    def _rebuild(annotation: object) -> None:
        if annotation is None or annotation is type(None):
            return
        if isinstance(annotation, type) and issubclass(annotation, BaseModel) and annotation not in seen:
            seen.add(annotation)
            annotation.model_rebuild()
            return
        for arg in typing.get_args(annotation):
            _rebuild(arg)

    for provider in server.providers:
        # FastMCP exposes only an async `list_tools()`; the sync source of truth
        # is `_components` on each LocalProvider. Read via `getattr` so the
        # type-checker doesn't reject the protocol-typed `provider` here.
        components = getattr(provider, "_components", None)
        if not components:
            continue
        for component in components.values():
            _rebuild(getattr(component, "return_type", None))


def _annotate_read_only_hints(server: FastMCP) -> None:
    """Stamp each registered tool's `readOnlyHint` annotation from the name-based read/write classifier.

    kodo's per-action confirmation gate skips tools that advertise `readOnlyHint=True`, but the
    ~315 hand-written typed tools carry no annotations, so every read would still prompt. Rather than
    edit each `@mcp.tool()` site, this single post-registration pass sets the hint in place from the
    same `is_read_tool` verb heuristic the read-only middleware already trusts: reads -> `True`,
    writes -> `False`. This covers whichever version tree (v41/v42/v43) is mounted.

    An already-annotated tool is respected — the hint is set only when a tool has no annotations or a
    `readOnlyHint` that is still unset — so a deliberate hand-set annotation is never overwritten. Tool
    objects are mutable pydantic models here (FastMCP 3.4.x), so the annotation is attached in place.
    Reads from `server.providers[*]._components` for the same synchronous, in-async-context reasons as
    `_eager_rebuild_tool_return_types`.
    """
    for provider in server.providers:
        components = getattr(provider, "_components", None)
        if not components:
            continue
        for component in components.values():
            if not isinstance(component, Tool):
                continue
            annotations = component.annotations
            if annotations is not None and annotations.readOnlyHint is not None:
                continue  # respect a hand-set hint
            read_only = is_read_tool(component.name)
            if annotations is None:
                component.annotations = ToolAnnotations(readOnlyHint=read_only)
            else:
                annotations.readOnlyHint = read_only


if __name__ == "__main__":
    main()
