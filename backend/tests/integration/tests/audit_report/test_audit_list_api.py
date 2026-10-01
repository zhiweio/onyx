"""Audit report list endpoints: server-side pagination, search, totals."""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.db.enums import ApprovalDecision
from onyx.db.models import (
    ActionApproval,
    BuildSession,
    PlatformToolLog,
    SearchQuery,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from shared_configs.contextvars import CURRENT_TENANT_ID_CONTEXTVAR
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

_CREATED_LOG_IDS: list[int] = []
_CREATED_QUERY_IDS: list[UUID] = []
_CREATED_APPROVAL_IDS: list[UUID] = []
_CREATED_SESSION_IDS: list[UUID] = []


@pytest.fixture(autouse=True)
def _db_access() -> Generator[None, None, None]:
    SqlEngine.init_engine(pool_size=10, max_overflow=5)
    token = CURRENT_TENANT_ID_CONTEXTVAR.set(POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE)
    try:
        yield
    finally:
        CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


@pytest.fixture(autouse=True)
def _cleanup(_db_access: None) -> Generator[None, None, None]:
    yield
    with get_session_with_current_tenant() as db_session:
        db_session.execute(
            delete(PlatformToolLog).where(PlatformToolLog.id.in_(_CREATED_LOG_IDS))
        )
        db_session.execute(
            delete(SearchQuery).where(SearchQuery.id.in_(_CREATED_QUERY_IDS))
        )
        db_session.execute(
            delete(ActionApproval).where(
                ActionApproval.approval_id.in_(_CREATED_APPROVAL_IDS)
            )
        )
        db_session.execute(
            delete(BuildSession).where(BuildSession.id.in_(_CREATED_SESSION_IDS))
        )
        db_session.commit()
    _CREATED_LOG_IDS.clear()
    _CREATED_QUERY_IDS.clear()
    _CREATED_APPROVAL_IDS.clear()
    _CREATED_SESSION_IDS.clear()


def _seed_tool_call(user_id: str, tool: str, ok: bool, excerpt: str = "") -> None:
    with get_session_with_current_tenant() as db_session:
        row = PlatformToolLog(
            user_id=user_id,
            tool=tool,
            ok=ok,
            result_excerpt=excerpt,
        )
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        _CREATED_LOG_IDS.append(row.id)


def _seed_query(user_id: str, query: str) -> None:
    with get_session_with_current_tenant() as db_session:
        row = SearchQuery(user_id=user_id, query=query)
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        _CREATED_QUERY_IDS.append(row.id)


def _seed_approval(user_id: str, app_name: str) -> None:
    with get_session_with_current_tenant() as db_session:
        session = BuildSession(user_id=user_id, name=f"audit-test-{uuid4()}")
        db_session.add(session)
        db_session.flush()
        _CREATED_SESSION_IDS.append(session.id)
        approval = ActionApproval(
            session_id=session.id,
            app_name=app_name,
            actions=[{"id": "test-action"}],
            payload={"test": True},
            decision=ApprovalDecision.APPROVED,
        )
        db_session.add(approval)
        db_session.commit()
        db_session.refresh(approval)
        _CREATED_APPROVAL_IDS.append(approval.approval_id)


def test_tool_calls_pagination_search_and_totals(
    admin_user: DATestUser,
) -> None:
    marker = f"auditpage{uuid4().hex[:8]}"
    for index in range(5):
        _seed_tool_call(
            admin_user.id,
            tool=f"{marker}_tool_{index}",
            ok=index % 2 == 0,
            excerpt=f"excerpt-{marker}-{index}",
        )

    response = client.get(
        f"{API_SERVER_URL}/api/admin/audit/tool-calls",
        headers=admin_user.headers,
        params={"limit": 2, "offset": 0, "q": marker},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"items", "total_items", "stats"}
    assert body["total_items"] == 5
    assert len(body["items"]) == 2
    assert all(marker in call["tool"] for call in body["items"])

    # Second page returns the remaining rows.
    page_two = client.get(
        f"{API_SERVER_URL}/api/admin/audit/tool-calls",
        headers=admin_user.headers,
        params={"limit": 2, "offset": 2, "q": marker},
    ).json()
    assert page_two["total_items"] == 5
    assert len(page_two["items"]) == 2

    # Search narrows both rows and total.
    narrowed = client.get(
        f"{API_SERVER_URL}/api/admin/audit/tool-calls",
        headers=admin_user.headers,
        params={"limit": 10, "offset": 0, "q": f"{marker}_tool_3"},
    ).json()
    assert narrowed["total_items"] == 1
    assert [call["tool"] for call in narrowed["items"]] == [f"{marker}_tool_3"]

    # Stats aggregate the seeded window.
    stats_by_tool = {stat["tool"]: stat for stat in narrowed["stats"]}
    assert stats_by_tool[f"{marker}_tool_3"]["calls"] == 1


def test_query_history_fuzzy_search_and_totals(
    admin_user: DATestUser,
) -> None:
    marker = f"auditq{uuid4().hex[:8]}"
    _seed_query(admin_user.id, f"{marker} quarterly report")
    _seed_query(admin_user.id, f"unrelated {marker} budget")

    response = client.get(
        f"{API_SERVER_URL}/api/admin/audit/query-history",
        headers=admin_user.headers,
        params={"limit": 1, "offset": 0, "q": marker},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_items"] == 2
    assert len(body["items"]) == 1
    assert marker in body["items"][0]["query"]

    exact = client.get(
        f"{API_SERVER_URL}/api/admin/audit/query-history",
        headers=admin_user.headers,
        params={"limit": 10, "offset": 0, "q": "quarterly"},
    ).json()
    assert exact["total_items"] >= 1


def test_approvals_envelope_search_and_totals(
    admin_user: DATestUser,
) -> None:
    marker = f"auditapp{uuid4().hex[:8]}"
    _seed_approval(admin_user.id, f"{marker}-webhook")
    _seed_approval(admin_user.id, f"{marker}-email")

    response = client.get(
        f"{API_SERVER_URL}/api/admin/audit/approvals",
        headers=admin_user.headers,
        params={"limit": 1, "offset": 0, "q": f"{marker}-webhook"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_items"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["app_name"] == f"{marker}-webhook"
    assert body["items"][0]["decision"] == "APPROVED"


def test_quarantines_returns_paginated_envelope(
    admin_user: DATestUser,  # noqa: ARG001
) -> None:
    response = client.get(
        f"{API_SERVER_URL}/api/admin/audit/quarantines",
        headers=admin_user.headers,
        params={"limit": 5, "offset": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total_items" in body
