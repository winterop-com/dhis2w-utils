"""FastMCP tool registration for the `files` plugin.

Binary upload/download tools intentionally omit-ed — MCP tools exchange JSON,
so pushing/pulling multi-MB blobs through a tool call is the wrong shape.
Operators who need upload/download reach for the CLI (`d2w files documents
upload ...`) or the Python library. MCP tools here cover the metadata-only
operations agents actually benefit from: listing documents, pulling their
metadata, creating external-URL links, and deleting stale entries.
"""

from __future__ import annotations

from typing import Any

from dhis2w_client.v42 import Document, FileResource

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v42.plugins.files import service


def register(mcp: Any) -> None:
    """Register files tools on the MCP server."""

    @mcp.tool()
    async def files_documents_list(
        filter: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        profile: str | None = None,
    ) -> list[Document]:
        """List DHIS2 documents (`/api/documents`).

        `filter` accepts DHIS2 filter syntax (`name:like:Annual`). `page` is
        1-indexed; `page_size` defaults to 50 on the DHIS2 side.
        """
        return await service.list_documents(
            resolve_profile(profile),
            filter=filter,
            page=page,
            page_size=page_size,
        )

    @mcp.tool()
    async def files_documents_get(uid: str, profile: str | None = None) -> Document:
        """Return typed metadata for one document by UID."""
        return await service.get_document(resolve_profile(profile), uid)

    @mcp.tool()
    async def files_documents_create_external(
        name: str,
        url: str,
        profile: str | None = None,
    ) -> Document:
        """Create an EXTERNAL_URL document — no bytes uploaded, DHIS2 links out to `url`."""
        return await service.create_external_document(resolve_profile(profile), name=name, url=url)

    @mcp.tool()
    async def files_documents_delete(uid: str, profile: str | None = None) -> dict[str, str]:
        """Delete one document by UID."""
        await service.delete_document(resolve_profile(profile), uid)
        return {"status": "deleted", "uid": uid}

    @mcp.tool()
    async def files_resources_get(uid: str, profile: str | None = None) -> FileResource:
        """Return typed metadata for one file resource (`/api/fileResources/{uid}`)."""
        return await service.get_file_resource(resolve_profile(profile), uid)
