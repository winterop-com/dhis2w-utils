"""Unit tests for the SQLAlchemy+aiosqlite TokenStore."""

from __future__ import annotations

import os
from pathlib import Path

from dhis2w_client.v42.auth.oauth2 import OAuth2Token
from dhis2w_core.token_store import SqliteTokenStore


async def test_round_trip_get_set(tmp_path: Path) -> None:
    """Round trip get set."""
    store = SqliteTokenStore(tmp_path / "tokens.sqlite")
    try:
        assert await store.get("profile:prod") is None
        await store.set(
            "profile:prod",
            OAuth2Token(access_token="at1", refresh_token="rt1", expires_at=1.0),
        )
        got = await store.get("profile:prod")
        assert got is not None
        assert got.access_token == "at1"
        assert got.refresh_token == "rt1"
        assert got.expires_at == 1.0
    finally:
        await store.close()


async def test_upsert_replaces_existing(tmp_path: Path) -> None:
    """Upsert replaces existing."""
    store = SqliteTokenStore(tmp_path / "tokens.sqlite")
    try:
        await store.set("k", OAuth2Token(access_token="v1", refresh_token="r1", expires_at=1.0))
        await store.set("k", OAuth2Token(access_token="v2", refresh_token="r2", expires_at=2.0))
        got = await store.get("k")
        assert got is not None
        assert got.access_token == "v2"
        assert got.refresh_token == "r2"
        assert got.expires_at == 2.0
    finally:
        await store.close()


async def test_delete_returns_true_if_present(tmp_path: Path) -> None:
    """Delete returns true if present."""
    store = SqliteTokenStore(tmp_path / "tokens.sqlite")
    try:
        await store.set("k", OAuth2Token(access_token="v", refresh_token="r", expires_at=1.0))
        assert await store.delete("k") is True
        assert await store.delete("k") is False
        assert await store.get("k") is None
    finally:
        await store.close()


async def test_db_file_perms_are_0600(tmp_path: Path) -> None:
    """Db file perms are 0600."""
    store = SqliteTokenStore(tmp_path / "nested" / "tokens.sqlite")
    try:
        await store.set("k", OAuth2Token(access_token="v", refresh_token=None, expires_at=1.0))
    finally:
        await store.close()
    path = tmp_path / "nested" / "tokens.sqlite"
    assert path.exists()
    # On some filesystems (e.g. FAT) chmod is a no-op; only assert on unix-like.
    if os.name == "posix":
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
