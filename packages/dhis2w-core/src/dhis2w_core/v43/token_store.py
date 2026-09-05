"""SQLAlchemy + aiosqlite `TokenStore` impl for persisted OAuth2 tokens."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from dhis2w_client.v43.auth.oauth2 import OAuth2Token
from sqlalchemy import Float, String, select
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from dhis2w_core.profile import find_project_profiles_file, global_profiles_path

TOKENS_FILENAME = "tokens.sqlite"


class _Base(DeclarativeBase):
    """SQLAlchemy declarative base for the token-store schema."""


class _TokenRow(_Base):
    """One persisted OAuth2 token, keyed by `store_key` (e.g. 'profile:prod')."""

    __tablename__ = "oauth2_tokens"

    store_key: Mapped[str] = mapped_column(String, primary_key=True)
    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    client_id: Mapped[str | None] = mapped_column(String, nullable=True)


def _drop_table_without_identity_columns(connection: Connection) -> None:
    """Drop the token table when it lacks the identity columns, so `create_all` rebuilds it."""
    inspector = sqlalchemy_inspect(connection)
    if not inspector.has_table(_TokenRow.__tablename__):
        return
    columns = {column["name"] for column in inspector.get_columns(_TokenRow.__tablename__)}
    if {"base_url", "client_id"} <= columns:
        return
    _Base.metadata.tables[_TokenRow.__tablename__].drop(connection)


class SqliteTokenStore:
    """File-backed TokenStore conforming to `dhis2w_client.v42.auth.oauth2.TokenStore`.

    Creates the parent directory and DB file lazily on first access. After the
    DB file exists, perms are forced to 0600.

    Each row carries the instance origin and OAuth2 client id the token was
    minted for, so `OAuth2Auth` can tell one instance's bearer token from
    another's. A table that predates those columns is dropped and recreated on
    first access: a token whose identity is unknown is unusable anyway, and the
    next call runs the login flow again.
    """

    def __init__(self, db_path: Path) -> None:
        """Build an engine bound to `db_path` (not yet created)."""
        self._db_path = db_path
        self._initialized = False
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            future=True,
        )
        self._session_maker = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def db_path(self) -> Path:
        """Filesystem path of the backing sqlite DB."""
        return self._db_path

    async def _ensure_init(self) -> None:
        if self._initialized:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._engine.begin() as conn:
            await conn.run_sync(_drop_table_without_identity_columns)
            await conn.run_sync(_Base.metadata.create_all)
        if self._db_path.exists():
            with contextlib.suppress(OSError):
                os.chmod(self._db_path, 0o600)
        self._initialized = True

    async def get(self, key: str) -> OAuth2Token | None:
        """Return the stored token for `key`, or None if absent."""
        await self._ensure_init()
        async with self._session_maker() as session:
            result = await session.execute(select(_TokenRow).where(_TokenRow.store_key == key))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return OAuth2Token(
                access_token=row.access_token,
                refresh_token=row.refresh_token,
                expires_at=row.expires_at,
                base_url=row.base_url,
                client_id=row.client_id,
            )

    async def set(self, key: str, token: OAuth2Token) -> None:
        """Upsert the token for `key`."""
        await self._ensure_init()
        async with self._session_maker() as session:
            existing = await session.get(_TokenRow, key)
            refresh = token.refresh_token
            if existing is None:
                session.add(
                    _TokenRow(
                        store_key=key,
                        access_token=token.access_token,
                        refresh_token=refresh,
                        expires_at=token.expires_at,
                        base_url=token.base_url,
                        client_id=token.client_id,
                    )
                )
            else:
                existing.access_token = token.access_token
                existing.refresh_token = refresh
                existing.expires_at = token.expires_at
                existing.base_url = token.base_url
                existing.client_id = token.client_id
            await session.commit()

    async def delete(self, key: str) -> bool:
        """Delete the entry for `key`; returns True if something was removed."""
        await self._ensure_init()
        async with self._session_maker() as session:
            existing = await session.get(_TokenRow, key)
            if existing is None:
                return False
            await session.delete(existing)
            await session.commit()
            return True

    async def close(self) -> None:
        """Dispose of the underlying async engine."""
        await self._engine.dispose()


def token_store_for_scope(scope: str, *, start: Path | None = None) -> SqliteTokenStore:
    """Return a `SqliteTokenStore` sited next to the profile file for the given scope.

    - `scope="project"`: nearest `.dhis2/tokens.sqlite` walking up from `start` (or
      `$PWD`), or `./.dhis2/tokens.sqlite` if no project profiles file exists yet.
    - `scope="global"`: `~/.config/dhis2/tokens.sqlite`.
    """
    if scope == "project":
        profiles_path = find_project_profiles_file(start)
        base = profiles_path.parent if profiles_path is not None else (start or Path.cwd()) / ".dhis2"
        return SqliteTokenStore(base / TOKENS_FILENAME)
    if scope == "global":
        return SqliteTokenStore(global_profiles_path().parent / TOKENS_FILENAME)
    raise ValueError(f"unknown scope {scope!r}; expected 'project' or 'global'")
