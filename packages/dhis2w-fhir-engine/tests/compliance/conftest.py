"""Pytest configuration for compliance tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest for compliance tests."""
    config.addinivalue_line(
        "markers",
        "compliance: marks tests as compliance tests (run with `pytest -m compliance`)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Add compliance marker to all tests in this directory."""
    for item in items:
        if "compliance" in str(item.fspath):
            item.add_marker(pytest.mark.compliance)
