"""Typed result models for the security plugin, shared across version trees."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CategoryMatch(BaseModel):
    """One risk category an account or role falls into, plus the authorities that matched."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    description: str
    matched: list[str]


class AccountAuthorities(BaseModel):
    """Effective authorities of the authenticated account, categorised by security risk."""

    model_config = ConfigDict(frozen=True)

    authorities: list[str]
    is_superuser: bool
    categories: list[CategoryMatch]
