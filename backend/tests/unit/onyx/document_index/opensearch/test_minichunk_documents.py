"""Unit tests for the multipass (mini chunk) OpenSearch support: the sibling
document model + ID scheme, the hit dedupe, and the query-level exclusions."""

from typing import Any, cast

from onyx.document_index.interfaces_new import TenantState
from onyx.document_index.opensearch.client import SearchHit
from onyx.document_index.opensearch.constants import DEFAULT_MAX_CHUNK_SIZE
from onyx.document_index.opensearch.opensearch_document_index import (
    DocumentQuery,
    _build_minichunk_documents_from_parent,
    _dedupe_minichunk_hits,
)
from onyx.document_index.opensearch.schema import (
    IS_MINI_CHUNK_FIELD_NAME,
    MINI_CHUNK_SIZE,
    DocumentChunk,
    MiniChunkDocument,
    get_opensearch_doc_chunk_id,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA

_TENANT_STATE = TenantState(tenant_id=POSTGRES_DEFAULT_SCHEMA, multitenant=False)


class _Filters:
    """Minimal IndexFilters stand-in: every scope empty."""

    access_control_list = None
    source_type = None
    tags = None
    document_set = None
    project_id_filter = None
    persona_id_filter = None
    created_at_range = None
    updated_at_range = None
    attached_document_ids = None
    hierarchy_node_ids = None
    forced_document_set = None


def _parent_chunk() -> DocumentChunk:
    return DocumentChunk(
        document_id="doc-1",
        chunk_index=2,
        title="Doc Title",
        title_vector=[0.3, 0.4],
        content="the full stored content",
        content_vector=[0.1, 0.2],
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


def _hit(
    document_id: str,
    chunk_index: int,
    score: float | None,
    is_mini: bool = False,
) -> SearchHit[DocumentChunk]:
    chunk = _parent_chunk()
    overrides: dict[str, Any] = {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content_vector": [0.0],
    }
    if is_mini:
        overrides["title_vector"] = None
        overrides["title"] = None
    document_chunk = chunk.model_copy(update=overrides)
    if is_mini:
        document_chunk = MiniChunkDocument(
            **document_chunk.model_dump(),
            is_mini_chunk=True,
            mini_chunk_index=0,
        )
    return SearchHit(document_chunk=document_chunk, score=score)


def test_get_opensearch_doc_chunk_id_minichunk_suffix() -> None:
    mini_id = get_opensearch_doc_chunk_id(
        tenant_state=_TENANT_STATE,
        document_id="doc-1",
        chunk_index=2,
        mini_chunk_index=1,
    )
    main_id = get_opensearch_doc_chunk_id(
        tenant_state=_TENANT_STATE, document_id="doc-1", chunk_index=2
    )
    assert mini_id != main_id
    assert mini_id == f"{main_id}_m1"


def test_minichunk_document_defaults() -> None:
    parent = _parent_chunk()
    [mini] = _build_minichunk_documents_from_parent(
        parent, mini_embeddings=[[0.9, 0.9]]
    )
    assert isinstance(mini, MiniChunkDocument)
    assert mini.is_mini_chunk is True
    assert mini.mini_chunk_index == 0
    assert mini.max_chunk_size == MINI_CHUNK_SIZE != DEFAULT_MAX_CHUNK_SIZE
    assert mini.content_vector == [0.9, 0.9]
    # Parent display fields are duplicated so a mini hit converts exactly like
    # its parent's.
    assert mini.content == parent.content
    assert mini.title == parent.title
    assert mini.chunk_index == parent.chunk_index
    assert mini.document_id == parent.document_id
    assert mini.access_control_list == parent.access_control_list


def test_minichunk_document_serialization_omits_parent_vectors() -> None:
    parent = _parent_chunk()
    [mini] = _build_minichunk_documents_from_parent(
        parent, mini_embeddings=[[0.9, 0.9]]
    )
    dumped: dict[str, Any] = mini.model_dump()
    # Vectors and marker fields are the only differences from the parent.
    assert "title_vector" not in dumped
    assert dumped["content_vector"] == [0.9, 0.9]
    assert dumped[IS_MINI_CHUNK_FIELD_NAME] is True
    assert "mini_chunk_index" in dumped


def test_dedupe_minichunk_hits_maps_minis_to_parent() -> None:
    hits = [
        _hit("doc-1", 2, score=5.0),
        _hit("doc-1", 2, score=7.0, is_mini=True),
        _hit("doc-1", 2, score=6.0, is_mini=True),
        _hit("doc-2", 0, score=4.0, is_mini=True),
    ]
    deduped = _dedupe_minichunk_hits(cast(Any, hits))
    assert len(deduped) == 2
    # Best score wins per (document_id, chunk_index) identity.
    assert deduped[0].score == 7.0
    # Order follows each identity's first appearance.
    assert deduped[0].document_chunk.document_id == "doc-1"
    assert deduped[1].document_chunk.document_id == "doc-2"


def test_dedupe_minichunk_hits_prefers_parent_when_higher() -> None:
    hits = [
        _hit("doc-1", 0, score=9.0),
        _hit("doc-1", 0, score=2.0, is_mini=True),
    ]
    [deduped] = _dedupe_minichunk_hits(cast(Any, hits))
    assert deduped.score == 9.0


def test_dedupe_minichunk_hits_handles_none_scores() -> None:
    hits = [
        _hit("doc-1", 0, score=None),
        _hit("doc-1", 0, score=None, is_mini=True),
    ]
    [deduped] = _dedupe_minichunk_hits(cast(Any, hits))
    assert deduped.score is None


def test_keyword_search_query_excludes_minichunks() -> None:
    query = DocumentQuery.get_keyword_search_query(
        query_text="hello",
        num_hits=10,
        tenant_state=_TENANT_STATE,
        index_filters=cast(Any, _Filters()),
        include_hidden=False,
    )
    must_not = query["query"]["bool"]["must_not"]
    assert {"term": {IS_MINI_CHUNK_FIELD_NAME: {"value": True}}} in must_not


def test_random_search_query_excludes_minichunks() -> None:
    query = DocumentQuery.get_random_search_query(
        tenant_state=_TENANT_STATE,
        index_filters=cast(Any, _Filters()),
        num_to_retrieve=10,
    )
    bool_query = query["query"]["function_score"]["query"]["bool"]
    assert {"term": {IS_MINI_CHUNK_FIELD_NAME: {"value": True}}} in bool_query[
        "must_not"
    ]


def test_get_from_document_id_query_excludes_minichunks() -> None:
    query = DocumentQuery.get_from_document_id_query(
        document_id="doc-1",
        tenant_state=_TENANT_STATE,
        index_filters=cast(Any, _Filters()),
        include_hidden=False,
        max_chunk_size=DEFAULT_MAX_CHUNK_SIZE,
        min_chunk_index=None,
        max_chunk_index=None,
    )
    must_not = query["query"]["bool"]["must_not"]
    assert {"term": {IS_MINI_CHUNK_FIELD_NAME: {"value": True}}} in must_not


def test_delete_from_document_id_query_keeps_minichunks() -> None:
    """Deletion must reach the mini chunk siblings; no exclusion is allowed."""
    query = DocumentQuery.delete_from_document_id_query(
        document_id="doc-1",
        tenant_state=_TENANT_STATE,
    )
    assert "must_not" not in query["query"]["bool"]
