"""Generated Dhis2OAuth2Authorization model for DHIS2 v43. Do not edit by hand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import Reference


class Dhis2OAuth2Authorization(BaseModel):
    """Generated model for DHIS2 `Dhis2OAuth2Authorization`.

    DHIS2 Dhis2 O Auth2 Authorization - persisted metadata (generated from /api/schemas at DHIS2 v43).

    API endpoint: /api/oAuth2Authorizations.

    Field `Field(description=...)` entries flag DHIS2 semantics the bare
    type can't capture: which side of a relationship owns the link
    (writable) vs the inverse side (ignored by the API), uniqueness
    constraints, and length bounds.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    access: Any | None = Field(default=None, description="Reference to Access. Read-only (inverse side).")
    accessTokenExpiresAt: datetime | None = None
    accessTokenIssuedAt: datetime | None = None
    accessTokenScopes: str | None = Field(default=None, description="Length/value max=1000.")
    accessTokenType: str | None = Field(default=None, description="Length/value max=255.")
    attributeValues: Any | None = Field(
        default=None, description="Reference to AttributeValues. Read-only (inverse side)."
    )
    authorizationCodeExpiresAt: datetime | None = None
    authorizationCodeIssuedAt: datetime | None = None
    authorizationGrantType: str | None = Field(default=None, description="Length/value max=255.")
    authorizedScopes: str | None = Field(default=None, description="Length/value max=1000.")
    code: str | None = Field(default=None, description="Unique. Length/value max=50.")
    created: datetime | None = None
    createdBy: Reference | None = Field(default=None, description="Reference to User.")
    deviceCodeExpiresAt: datetime | None = None
    deviceCodeIssuedAt: datetime | None = None
    displayName: str | None = Field(default=None, description="Read-only.")
    favorite: bool | None = Field(default=None, description="Read-only.")
    favorites: list[Any] | None = Field(default=None, description="Collection of String. Read-only (inverse side).")
    href: str | None = None
    id: str | None = Field(default=None, description="Unique. Length/value min=11, max=11.")
    lastUpdated: datetime | None = None
    lastUpdatedBy: Reference | None = Field(default=None, description="Reference to User.")
    name: str | None = Field(default=None, description="Length/value min=1, max=230.")
    oidcIdTokenExpiresAt: datetime | None = None
    oidcIdTokenIssuedAt: datetime | None = None
    principalName: str | None = Field(default=None, description="Length/value max=255.")
    refreshTokenExpiresAt: datetime | None = None
    refreshTokenIssuedAt: datetime | None = None
    registeredClientId: str | None = Field(default=None, description="Length/value max=255.")
    sharing: Any | None = Field(default=None, description="Reference to Sharing. Read-only (inverse side).")
    translations: list[Any] | None = Field(
        default=None, description="Collection of Translation. Read-only (inverse side)."
    )
    user: Reference | None = Field(default=None, description="Reference to User. Read-only (inverse side).")
    userCodeExpiresAt: datetime | None = None
    userCodeIssuedAt: datetime | None = None
