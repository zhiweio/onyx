"""Integration tests for the multipass (mini chunk) OpenSearch support.

Assumes OpenSearch is running (same requirement as test_opensearch_client.py).
Covers the end-to-end mini chunk lifecycle: sibling-document writes, semantic
retrieval mapping a mini hit back to its parent, keyword/ID-based exclusion,
metadata update sync, and deletion.
"""

import uuid
from collections.abc import Generator

import pytest
from opensearchpy import NotFoundError

from onyx.context.search.models import IndexFilters
from onyx.db.enums import EmbeddingPrecision
from onyx.document_index.interfaces_new import (
    DocumentSectionRequest,
    MetadataUpdateRequest,
    TenantState,
)
from onyx.document_index.opensearch.client import (
    wait_for_opensearch_with_timeout,
)
from onyx.document_index.opensearch.opensearch_document_index import (
    OpenSearchDocumentIndex,
)
from onyx.document_index.opensearch.schema import (
    DocumentChunk,
    MiniChunkDocument,
    get_opensearch_doc_chunk_id,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA

_DIM = 128
_TENANT_STATE = TenantState(tenant_id=POSTGRES_DEFAULT_SCHEMA, multitenant=False)

# Orthogonal directions, so cosine distance is unambiguous.
_QUERY_VECTOR = [1.0] + [0.0] * (_DIM - 1)
_FAR_VECTOR = [0.0, 1.0] + [0.0] * (_DIM - 2)


def _parent_chunk(
    document_id: str = "doc-1",
    chunk_index: int = 0,
    content_vector: list[float] | None = None,
    content: str = "the quick brown fox jumps over the lazy dog",
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_index=chunk_index,
        title="Doc Title",
        title_vector=[0.5] * _DIM,
        content=content,
        content_vector=content_vector or _FAR_VECTOR,
        source_type="file",
        metadata_list=None,
        last_updated=None,
        created_at=None,
        public=True,
        access_control_list=[],
        hidden=False,
        global_boost=0,
        semantic_identifier="Doc semantic id",
        image_file_id=None,
        source_links=None,
        blurb="blurb",
        doc_summary="",
        chunk_context="",
        metadata_suffix=None,
        tenant_id=_TENANT_STATE,
    )


def _mini_document(
    parent: DocumentChunk,
    mini_chunk_index: int,
    content_vector: list[float],
) -> MiniChunkDocument:
    return MiniChunkDocument(
        document_id=parent.document_id,
        chunk_index=parent.chunk_index,
        title=parent.title,
        content=parent.content,
        content_vector=content_vector,
        source_type=parent.source_type,
        metadata_list=parent.metadata_list,
        last_updated=parent.last_updated,
        created_at=parent.created_at,
        public=parent.public,
        access_control_list=parent.access_control_list,
        hidden=parent.hidden,
        global_boost=parent.global_boost,
        semantic_identifier=parent.semantic_identifier,
        image_file_id=parent.image_file_id,
        source_links=parent.source_links,
        blurb=parent.blurb,
        doc_summary=parent.doc_summary,
        chunk_context=parent.chunk_context,
        metadata_suffix=parent.metadata_suffix,
        tenant_id=parent.tenant_id,
        mini_chunk_index=mini_chunk_index,
    )


@pytest.fixture(scope="module")
def opensearch_available() -> None:
    """Verifies OpenSearch is running, skips all tests if not."""
    if not wait_for_opensearch_with_timeout():
        pytest.fail("OpenSearch is not available.")


@pytest.fixture(scope="function")
def doc_index(
    opensearch_available: None,  # noqa: ARG001
) -> Generator[OpenSearchDocumentIndex, None, None]:
    index_name = f"test_minichunk_{uuid.uuid4().hex[:8]}"
    index = OpenSearchDocumentIndex(
        tenant_state=_TENANT_STATE,
        index_name=index_name,
        embedding_dim=_DIM,
        embedding_precision=EmbeddingPrecision.FLOAT,
    )
    index.verify_and_create_index_if_necessary(
        embedding_dim=_DIM,
        embedding_precision=EmbeddingPrecision.FLOAT,
    )
    yield index
    try:
        index._client.delete_index()
    except Exception:
        pass
    finally:
        index._client.close()


def _refresh(index: OpenSearchDocumentIndex) -> None:
    index._client.refresh_index()


def test_semantic_retrieval_maps_minichunk_hit_to_parent(
    doc_index: OpenSearchDocumentIndex,
) -> None:
    """A mini chunk vector close to the query surfaces the PARENT chunk (same
    identity and content), with no duplicate hit for the mini itself."""
    parent = _parent_chunk()
    minis = [
        _mini_document(parent, 0, content_vector=_QUERY_VECTOR),
        _mini_document(parent, 1, content_vector=_FAR_VECTOR),
    ]
    doc_index.index_raw_chunks([parent, *minis])
    _refresh(doc_index)

    hits = doc_index.semantic_retrieval(
        query_embedding=_QUERY_VECTOR,
        filters=IndexFilters(access_control_list=None),
        num_to_retrieve=10,
    )

    assert len(hits) == 1
    assert hits[0].document_id == parent.document_id
    assert hits[0].chunk_id == parent.chunk_index
    assert hits[0].content == parent.content


def test_semantic_retrieval_dedupes_parent_and_minichunk(
    doc_index: OpenSearchDocumentIndex,
) -> None:
    """When both the parent and its minis match, the parent appears once."""
    parent = _parent_chunk(content_vector=_QUERY_VECTOR)
    minis = [
        _mini_document(parent, 0, content_vector=_QUERY_VECTOR),
        _mini_document(parent, 1, content_vector=_QUERY_VECTOR),
    ]
    doc_index.index_raw_chunks([parent, *minis])
    _refresh(doc_index)

    hits = doc_index.semantic_retrieval(
        query_embedding=_QUERY_VECTOR,
        filters=IndexFilters(access_control_list=None),
        num_to_retrieve=10,
    )

    assert len(hits) == 1
    assert hits[0].document_id == parent.document_id
    assert hits[0].chunk_id == parent.chunk_index


def test_keyword_retrieval_excludes_minichunks(
    doc_index: OpenSearchDocumentIndex,
) -> None:
    """Keyword search counts the parent once even with matching mini siblings."""
    parent = _parent_chunk()
    minis = [
        _mini_document(parent, 0, content_vector=_QUERY_VECTOR),
        _mini_document(parent, 1, content_vector=_QUERY_VECTOR),
    ]
    doc_index.index_raw_chunks([parent, *minis])
    _refresh(doc_index)

    hits = doc_index.keyword_retrieval(
        query="quick brown fox",
        filters=IndexFilters(access_control_list=None),
        num_to_retrieve=10,
    )

    assert len(hits) == 1
    assert hits[0].document_id == parent.document_id


def test_id_based_retrieval_excludes_minichunks(
    doc_index: OpenSearchDocumentIndex,
) -> None:
    parent = _parent_chunk()
    minis = [_mini_document(parent, 0, content_vector=_QUERY_VECTOR)]
    doc_index.index_raw_chunks([parent, *minis])
    _refresh(doc_index)

    hits = doc_index.id_based_retrieval(
        chunk_requests=[DocumentSectionRequest(document_id=parent.document_id)],
        filters=IndexFilters(access_control_list=None),
    )

    assert len(hits) == 1
    assert hits[0].chunk_id == parent.chunk_index


def test_metadata_update_syncs_minichunks(
    doc_index: OpenSearchDocumentIndex,
) -> None:
    """Hiding a document reaches its mini chunk siblings too — a stale visible
    mini would leak hidden content through semantic search."""
    parent = _parent_chunk()
    minis = [_mini_document(parent, 0, content_vector=_QUERY_VECTOR)]
    doc_index.index_raw_chunks([parent, *minis])
    _refresh(doc_index)

    # Sanity: the mini is searchable before the update.
    assert (
        len(
            doc_index.semantic_retrieval(
                query_embedding=_QUERY_VECTOR,
                filters=IndexFilters(access_control_list=None),
                num_to_retrieve=10,
            )
        )
        == 1
    )

    doc_index.update(
        [
            MetadataUpdateRequest(
                document_ids=[parent.document_id],
                doc_id_to_chunk_cnt={parent.document_id: 1},
                hidden=True,
            )
        ]
    )
    _refresh(doc_index)

    hits = doc_index.semantic_retrieval(
        query_embedding=_QUERY_VECTOR,
        filters=IndexFilters(access_control_list=None),
        num_to_retrieve=10,
    )
    assert hits == []


def test_delete_removes_minichunks(doc_index: OpenSearchDocumentIndex) -> None:
    parent = _parent_chunk()
    minis = [_mini_document(parent, 0, content_vector=_QUERY_VECTOR)]
    doc_index.index_raw_chunks([parent, *minis])
    _refresh(doc_index)

    doc_index.delete(parent.document_id)
    _refresh(doc_index)

    mini_id = get_opensearch_doc_chunk_id(
        tenant_state=_TENANT_STATE,
        document_id=parent.document_id,
        chunk_index=parent.chunk_index,
        mini_chunk_index=0,
    )
    with pytest.raises(NotFoundError):
        doc_index._client.get_document(mini_id)
    assert (
        doc_index.id_based_retrieval(
            chunk_requests=[DocumentSectionRequest(document_id=parent.document_id)],
            filters=IndexFilters(access_control_list=None),
        )
        == []
    )
