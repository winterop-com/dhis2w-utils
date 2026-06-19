"""Guard the PEP 562 lazy import surfaces against map drift.

The top-level `dhis2w_client` package and each per-version surface
(`dhis2w_client.v41` / `v42` / `v43`) are lazy modules: `__all__` lists the
public surface, `_LAZY_EXPORTS` maps each name to the module that defines it,
and `__getattr__` resolves a name on first access. A `TYPE_CHECKING` block
re-exports the same names so type checkers and IDEs see real symbols.

That split is the risk these tests cover: a symbol added to `__all__` and the
`TYPE_CHECKING` block but forgotten in `_LAZY_EXPORTS` passes type checking yet
raises `AttributeError` at runtime. Asserting the map matches `__all__` and
that every name resolves catches the drift in CI instead of at import time.
"""

from __future__ import annotations

import importlib

import pytest

_LAZY_MODULES = [
    "dhis2w_client",
    "dhis2w_client.v41",
    "dhis2w_client.v42",
    "dhis2w_client.v43",
]


@pytest.mark.parametrize("module_name", _LAZY_MODULES)
def test_lazy_map_matches_all(module_name: str) -> None:
    """`_LAZY_EXPORTS` keys are exactly `__all__` — no missing or stray entries."""
    module = importlib.import_module(module_name)
    lazy_exports = module._LAZY_EXPORTS
    public_surface = module.__all__
    assert set(lazy_exports) == set(public_surface)


@pytest.mark.parametrize("module_name", _LAZY_MODULES)
def test_every_export_resolves(module_name: str) -> None:
    """Every name in `__all__` resolves via `__getattr__` without error."""
    module = importlib.import_module(module_name)
    for name in module.__all__:
        assert getattr(module, name) is not None


@pytest.mark.parametrize("module_name", _LAZY_MODULES)
def test_unknown_attribute_raises(module_name: str) -> None:
    """`__getattr__` raises `AttributeError` for names outside the surface."""
    module = importlib.import_module(module_name)
    with pytest.raises(AttributeError):
        _ = module.ThisSymbolDoesNotExist
