"""Admin API tests for the craft eval pipeline (P4).

Covers catalog listing, permission boundaries, and input validation. The
trigger endpoint is validated on its rejection path only: a valid trigger
dispatches a real-model batch, which belongs to live e2e, not CI.
"""

from __future__ import annotations

from uuid import uuid4

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser


def test_list_cases_requires_admin() -> None:
    non_admin = UserManager.create(name=f"eval-nonadmin-{uuid4().hex[:8]}")
    response = client.get(
        f"{API_SERVER_URL}/build/admin/evals/cases",
        headers=non_admin.headers,
        cookies=non_admin.cookies,
    )
    assert response.status_code in (401, 403)


def test_list_cases_returns_packaged_golden_set(admin_user: DATestUser) -> None:
    response = client.get(
        f"{API_SERVER_URL}/build/admin/evals/cases",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 6
    slugs = {case["slug"] for case in cases}
    assert "tax-vat-filing-workpaper-golden" in slugs
    assert "biomed-clinical-initiation-golden" in slugs
    for case in cases:
        assert case["expected_paths"]
        assert case["rubric_criterion_count"] >= 5


def test_trigger_rejects_unknown_case_slug(admin_user: DATestUser) -> None:
    response = client.post(
        f"{API_SERVER_URL}/build/admin/evals/runs",
        json={"case_slugs": ["no-such-case"]},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert response.status_code in (400, 422)


def test_trigger_rejects_empty_selection(admin_user: DATestUser) -> None:
    response = client.post(
        f"{API_SERVER_URL}/build/admin/evals/runs",
        json={"case_slugs": []},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert response.status_code in (400, 422)


def test_get_unknown_run_returns_404(admin_user: DATestUser) -> None:
    response = client.get(
        f"{API_SERVER_URL}/build/admin/evals/runs/00000000-0000-4000-8000-000000000000",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert response.status_code == 404


def test_eval_session_transcript_requires_admin() -> None:
    non_admin = UserManager.create(name=f"eval-transcript-{uuid4().hex[:8]}")
    response = client.get(
        f"{API_SERVER_URL}/build/admin/evals/sessions/{uuid4()}/messages",
        headers=non_admin.headers,
        cookies=non_admin.cookies,
    )
    assert response.status_code in (401, 403)


def test_eval_session_transcript_unknown_session_returns_404(
    admin_user: DATestUser,
) -> None:
    response = client.get(
        f"{API_SERVER_URL}/build/admin/evals/sessions/00000000-0000-4000-8000-000000000000/messages",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert response.status_code == 404


def test_list_runs_requires_admin() -> None:
    bystander = UserManager.create(name=f"eval-bystander-{uuid4().hex[:8]}")
    response = client.get(
        f"{API_SERVER_URL}/build/admin/evals/runs",
        headers=bystander.headers,
        cookies=bystander.cookies,
    )
    assert response.status_code in (401, 403)
