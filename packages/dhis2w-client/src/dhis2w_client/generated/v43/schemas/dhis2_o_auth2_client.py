"""Generated Dhis2OAuth2Client model for DHIS2 v43. Do not edit by hand."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import Reference


class Dhis2OAuth2Client(BaseModel):
    """Generated model for DHIS2 `Dhis2OAuth2Client`.

    DHIS2 Dhis2 O Auth2 Client - persisted metadata (generated from /api/schemas at DHIS2 v43).

    API endpoint: /api/oAuth2Clients.

    Field `Field(description=...)` entries flag DHIS2 semantics the bare
    type can't capture: which side of a relationship owns the link
    (writable) vs the inverse side (ignored by the API), uniqueness
    constraints, and length bounds.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    access: Any | None = Field(default=None, description="Reference to Access. Read-only (inverse side).")
    attributeValues: Any | None = Field(
        default=None, description="Reference to AttributeValues. Read-only (inverse side)."
    )
    authorizationGrantTypes: str | None = Field(default=None, description="Length/value max=1000.")
    clientAuthenticationMethods: str | None = Field(default=None, description="Length/value max=1000.")
    clientId: str | None = Field(default=None, description="Unique. Length/value max=255.")
    clientIdIssuedAt: datetime | None = None
    clientSecret: str | None = Field(default=None, description="Length/value max=255.")
    clientSecretExpiresAt: datetime | None = None
    clientSettings: str | None = Field(default=None, description="Length/value max=2147483647.")
    code: str | None = Field(default=None, description="Unique. Length/value max=50.")
    created: datetime | None = None
    createdBy: Reference | None = Field(default=None, description="Reference to User.")
    displayName: str | None = Field(default=None, description="Read-only.")
    favorite: bool | None = Field(default=None, description="Read-only.")
    favorites: list[Any] | None = Field(default=None, description="Collection of String. Read-only (inverse side).")
    href: str | None = None
    id: str | None = Field(default=None, description="Unique. Length/value min=11, max=11.")
    lastUpdated: datetime | None = None
    lastUpdatedBy: Reference | None = Field(default=None, description="Reference to User.")
    name: str | None = Field(default=None, description="Length/value max=230.")
    postLogoutRedirectUris: str | None = Field(default=None, description="Length/value max=1000.")
    redirectUris: str | None = Field(default=None, description="Length/value max=1000.")
    scopes: str | None = Field(default=None, description="Length/value max=1000.")
    sharing: Any | None = Field(default=None, description="Reference to Sharing. Read-only (inverse side).")
    tokenSettings: str | None = Field(default=None, description="Length/value max=2147483647.")
    translations: list[Any] | None = Field(
        default=None, description="Collection of Translation. Read-only (inverse side)."
    )
    user: Reference | None = Field(default=None, description="Reference to User. Read-only (inverse side).")
