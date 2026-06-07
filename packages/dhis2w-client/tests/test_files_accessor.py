"""Tests for `Dhis2Client.files` — /api/documents + /api/fileResources accessors."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client, FileResourceDomain


def _auth() -> BasicAuth:
    """Throwaway BasicAuth for test clients."""
    return BasicAuth(username="a", password="b")


# ---- documents -----------------------------------------------------


@respx.mock
async def test_list_documents_returns_typed_models(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`list_documents` parses the `documents` array as `Document` pydantic models."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(
            200,
            json={
                "documents": [
                    {"id": "doc1", "name": "Annual report", "external": False, "attachment": True},
                    {"id": "doc2", "name": "Guide", "external": True, "url": "https://example.org/g"},
                ],
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        docs = await client.files.list_documents()
    finally:
        await client.close()

    assert [doc.id for doc in docs] == ["doc1", "doc2"]
    assert docs[0].external is False
    assert docs[1].external is True


@respx.mock
async def test_list_documents_forwards_filter_and_paging(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """filter / page / page_size reach DHIS2 as query params."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(200, json={"documents": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.files.list_documents(filter="name:like:x", page=2, page_size=10)
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["filter"] == "name:like:x"
    assert params["page"] == "2"
    assert params["pageSize"] == "10"


@respx.mock
async def test_upload_document_uses_two_step_fileresource_then_document(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`/api/documents` rejects multipart — upload routes through fileResource + JSON link.

    See BUGS.md #16. Flow:
    1. POST /api/fileResources with domain=DOCUMENT (multipart) -> fileResource uid
    2. POST /api/documents (JSON) with url=<fileResourceUid> -> document uid
    3. GET  /api/documents/{uid} -> typed Document
    """
    mock_system_info(server_version)
    fr_post = respx.post("https://dhis2.example/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "frDocUid0001"}}}),
    )
    respx.get("https://dhis2.example/api/fileResources/frDocUid0001").mock(
        return_value=httpx.Response(200, json={"id": "frDocUid0001", "domain": "DOCUMENT"}),
    )
    doc_post = respx.post("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(200, json={"response": {"uid": "newDocUid01"}}),
    )
    respx.get("https://dhis2.example/api/documents/newDocUid01").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "newDocUid01",
                "name": "report.pdf",
                "url": "frDocUid0001",
                "external": False,
                "attachment": True,
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        doc = await client.files.upload_document(b"hello world", name="report.pdf", filename="report.pdf")
    finally:
        await client.close()

    assert doc.id == "newDocUid01"
    # Step 1: multipart body went to /api/fileResources with domain=DOCUMENT.
    assert fr_post.call_count == 1
    assert fr_post.calls.last.request.url.params["domain"] == "DOCUMENT"
    assert b"hello world" in fr_post.calls.last.request.content
    # Step 2: JSON POST on /api/documents references the fileResource uid.
    assert doc_post.call_count == 1
    doc_body = doc_post.calls.last.request.content
    assert b'"url":"frDocUid0001"' in doc_body or b'"url": "frDocUid0001"' in doc_body
    assert "application/json" in doc_post.calls.last.request.headers.get("content-type", "")


@respx.mock
async def test_upload_document_raises_when_document_post_returns_no_uid(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """A malformed DHIS2 response on the document-create step surfaces a clear RuntimeError."""
    mock_system_info(server_version)
    respx.post("https://dhis2.example/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "frXx00000001"}}}),
    )
    respx.get("https://dhis2.example/api/fileResources/frXx00000001").mock(
        return_value=httpx.Response(200, json={"id": "frXx00000001", "domain": "DOCUMENT"}),
    )
    respx.post("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(200, json={"response": {}}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(RuntimeError, match="did not return a uid"):
            await client.files.upload_document(b"x", name="bad.bin", filename="bad.bin")
    finally:
        await client.close()


@respx.mock
async def test_create_external_document_posts_json_body(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """External-URL documents go through a JSON POST, not a multipart upload."""
    mock_system_info(server_version)
    post_route = respx.post("https://dhis2.example/api/documents").mock(
        return_value=httpx.Response(200, json={"response": {"uid": "extDoc00001"}}),
    )
    respx.get("https://dhis2.example/api/documents/extDoc00001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "extDoc00001", "name": "Wiki", "external": True, "url": "https://example.org"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        doc = await client.files.create_external_document(name="Wiki", url="https://example.org")
    finally:
        await client.close()

    assert doc.id == "extDoc00001"
    assert doc.external is True
    content_type = post_route.calls.last.request.headers.get("content-type", "")
    assert "application/json" in content_type


@respx.mock
async def test_download_document_returns_raw_bytes(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """The `/data` endpoint returns arbitrary bytes straight from `response.content`."""
    mock_system_info(server_version)
    payload = b"\x89PNG\r\n\x1a\n" + b"fake image data"
    respx.get("https://dhis2.example/api/documents/doc1/data").mock(
        return_value=httpx.Response(200, content=payload, headers={"Content-Type": "image/png"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        data = await client.files.download_document("doc1")
    finally:
        await client.close()

    assert data == payload


@respx.mock
async def test_delete_document(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete sends DELETE /api/documents/{uid} and returns without error."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/documents/doc1").mock(
        return_value=httpx.Response(200, json={}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.files.delete_document("doc1")
    finally:
        await client.close()

    assert route.call_count == 1


# ---- file resources ------------------------------------------------


@respx.mock
async def test_upload_file_resource_parses_nested_envelope(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """DHIS2 returns `response.fileResource.id` — NOT `response.uid` — on fileResource create."""
    mock_system_info(server_version)
    post_route = respx.post("https://dhis2.example/api/fileResources").mock(
        return_value=httpx.Response(
            202,
            json={"response": {"fileResource": {"id": "frNewUid00001"}}},
        ),
    )
    respx.get("https://dhis2.example/api/fileResources/frNewUid00001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "frNewUid00001",
                "name": "photo.png",
                "contentType": "image/png",
                "domain": "DATA_VALUE",
                "storageStatus": "STORED",
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        fr = await client.files.upload_file_resource(
            b"imgbytes",
            filename="photo.png",
            domain=FileResourceDomain.DATA_VALUE,
        )
    finally:
        await client.close()

    assert fr.id == "frNewUid00001"
    assert fr.domain == "DATA_VALUE"
    params = post_route.calls.last.request.url.params
    assert params["domain"] == "DATA_VALUE"


@respx.mock
async def test_upload_file_resource_accepts_string_domain(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Passing `domain='ICON'` string is equivalent to the enum member."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "iconFrUid001"}}}),
    )
    respx.get("https://dhis2.example/api/fileResources/iconFrUid001").mock(
        return_value=httpx.Response(
            200,
            json={"id": "iconFrUid001", "name": "icon.svg", "domain": "ICON"},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.files.upload_file_resource(b"<svg/>", filename="icon.svg", domain="ICON")
    finally:
        await client.close()

    assert route.calls.last.request.url.params["domain"] == "ICON"


@respx.mock
async def test_download_file_resource_returns_bytes(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """File-resource download returns raw bytes from `/data`."""
    mock_system_info(server_version)
    payload = b"raw_photo_bytes"
    respx.get("https://dhis2.example/api/fileResources/fr1/data").mock(
        return_value=httpx.Response(200, content=payload),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        data = await client.files.download_file_resource("fr1")
    finally:
        await client.close()

    assert data == payload


@respx.mock
async def test_get_file_resource_returns_typed_model(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Single-resource GET returns a typed `FileResource`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/fileResources/fr1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "fr1",
                "name": "attachment.pdf",
                "contentType": "application/pdf",
                "contentLength": 1234,
                "domain": "DATA_VALUE",
                "storageStatus": "STORED",
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        fr = await client.files.get_file_resource("fr1")
    finally:
        await client.close()

    assert fr.id == "fr1"
    assert fr.contentLength == 1234
    assert fr.domain == "DATA_VALUE"
