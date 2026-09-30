"""Standard answers admin list API: pagination, search, category filter."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import delete

from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.db.models import (
    StandardAnswer,
    StandardAnswer__StandardAnswerCategory,
    StandardAnswerCategory,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from shared_configs.contextvars import CURRENT_TENANT_ID_CONTEXTVAR
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

_CREATED_ANSWER_IDS: list[int] = []
_CREATED_CATEGORY_IDS: list[int] = []


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
            delete(StandardAnswer__StandardAnswerCategory).where(
                StandardAnswer__StandardAnswerCategory.standard_answer_id.in_(
                    _CREATED_ANSWER_IDS
                )
            )
        )
        db_session.execute(
            delete(StandardAnswer).where(StandardAnswer.id.in_(_CREATED_ANSWER_IDS))
        )
        db_session.execute(
            delete(StandardAnswerCategory).where(
                StandardAnswerCategory.id.in_(_CREATED_CATEGORY_IDS)
            )
        )
        db_session.commit()
    _CREATED_ANSWER_IDS.clear()
    _CREATED_CATEGORY_IDS.clear()


def _create_answer(
    admin_user: DATestUser, keyword: str, answer: str, category_ids: list[int] = None
) -> dict:
    if category_ids is None:
        category_ids = []
    response = client.post(
        f"{API_SERVER_URL}/api/admin/standard-answers",
        headers=admin_user.headers,
        json={"keyword": keyword, "answer": answer, "category_ids": category_ids},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    _CREATED_ANSWER_IDS.append(row["id"])
    return row


def _create_category(admin_user: DATestUser, name: str) -> dict:
    response = client.post(
        f"{API_SERVER_URL}/api/admin/standard-answers/categories",
        headers=admin_user.headers,
        json={"name": name},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    _CREATED_CATEGORY_IDS.append(row["id"])
    return row


def _list(
    admin_user: DATestUser,
    *,
    q: str | None = None,
    category_id: int | None = None,
    page_num: int = 0,
    page_size: int = 20,
) -> dict:
    params: dict[str, str | int] = {"page_num": page_num, "page_size": page_size}
    if q is not None:
        params["q"] = q
    if category_id is not None:
        params["category_id"] = category_id
    response = client.get(
        f"{API_SERVER_URL}/api/admin/standard-answers",
        headers=admin_user.headers,
        params=params,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_list_is_paginated_with_totals(admin_user: DATestUser) -> None:
    marker = "sapage"
    for index in range(3):
        _create_answer(admin_user, f"{marker}-{index}-wifi", f"answer {index}")

    body = _list(admin_user, q=marker, page_num=0, page_size=2)
    assert set(body.keys()) == {"items", "total_items"}
    assert body["total_items"] == 3
    assert len(body["items"]) == 2

    page_two = _list(admin_user, q=marker, page_num=1, page_size=2)
    assert page_two["total_items"] == 3
    assert len(page_two["items"]) == 1


def test_list_search_matches_keyword_and_answer(
    admin_user: DATestUser,
) -> None:
    marker = "sasearch"
    _create_answer(admin_user, f"{marker}-keyword", "the printer room answer")
    _create_answer(admin_user, "unrelated-keyword", f"{marker}-in-answer-body")

    body = _list(admin_user, q=marker)
    assert body["total_items"] == 2

    by_answer = _list(admin_user, q="printer room")
    assert by_answer["total_items"] == 1
    assert by_answer["items"][0]["keyword"] == f"{marker}-keyword"


def test_list_filters_by_category(admin_user: DATestUser) -> None:
    category = _create_category(admin_user, "audit-it-help")
    _create_answer(admin_user, "categorized-vpn", "vpn answer", [category["id"]])
    _create_answer(admin_user, "uncategorized-mail", "mail answer")

    body = _list(admin_user, category_id=category["id"])
    assert body["total_items"] == 1
    assert body["items"][0]["keyword"] == "categorized-vpn"
    assert body["items"][0]["category_ids"] == [category["id"]]

    without_category = _list(admin_user, q="uncategorized-mail")
    assert without_category["total_items"] == 1
    assert without_category["items"][0]["category_ids"] == []
