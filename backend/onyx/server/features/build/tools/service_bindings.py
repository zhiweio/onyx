"""Real service bindings for platform tools (search first).

The bridge builds a per-request registry so bindings close over the
requesting user; permission checks therefore run with that user's ACL,
which is what makes rag_search permission-aware.
"""

from __future__ import annotations

from typing import Any, Callable

from onyx.db.models import User
from onyx.server.features.build.tools.base import ToolContext
from onyx.utils.logger import setup_logger

logger = setup_logger()


def make_user_scoped_search_fn(user: User) -> Callable[..., list[dict[str, Any]]]:
    """Bind rag_search to the permission-aware search pipeline for ``user``.

    Document-set scoping rides through PersonaSearchInfo.document_set_names
    (the same path personas use), so a scenario's ``document_sets`` binding
    narrows retrieval exactly like a persona would. Failures surface as
    tool-level errors, never crashes.
    """

    def search(
        query: str,
        document_sets: list[str],
        limit: int,
        _ctx: ToolContext,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from onyx.context.search.models import ChunkSearchRequest, PersonaSearchInfo
        from onyx.context.search.pipeline import search_pipeline
        from onyx.db.engine.sql_engine import get_session_with_current_tenant
        from onyx.db.search_settings import get_current_search_settings
        from onyx.document_index.factory import get_default_document_index

        # get_session is a FastAPI Depends generator, not a context manager.
        with get_session_with_current_tenant() as db_session:
            fresh = db_session.execute(
                # fastapi-users types User.id as plain UUID under TYPE_CHECKING;
                # at runtime it is a mapped column.
                select(User).where(User.id == user.id)  # ty: ignore[invalid-argument-type]
            ).scalar_one_or_none()
            if fresh is None:
                raise RuntimeError("requesting user no longer exists")
            persona_info = PersonaSearchInfo(
                document_set_names=document_sets,
                search_start_date=None,
                attached_document_ids=[],
                hierarchy_node_ids=[],
            )
            chunks = search_pipeline(
                chunk_search_request=ChunkSearchRequest(
                    query=query,
                    limit=limit,
                ),
                document_index=get_default_document_index(
                    get_current_search_settings(db_session), None, db_session
                ),
                user=fresh,
                persona_search_info=persona_info,
                db_session=db_session,
            )
            hits: list[dict[str, Any]] = []
            for chunk in chunks:
                title = (
                    getattr(chunk, "semantic_identifier", None)
                    or getattr(chunk, "document_id", None)
                    or "document"
                )
                # document_id is the stable reference the web UI resolves to
                # a document view; no fabricated URL.
                doc_id = getattr(chunk, "document_id", None)
                hits.append(
                    {
                        "title": f"{title} [id: {doc_id}]" if doc_id else title,
                        "blurb": (getattr(chunk, "content", "") or "")[:400],
                    }
                )
            return hits

    return search
