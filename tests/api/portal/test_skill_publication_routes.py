import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.portal.endpoints import personal_skills, skills
from app.core.dependencies import require_api_key, require_permission


pytestmark = pytest.mark.no_infrastructure


async def _fake_user():
    return {"user_id": 7, "user_name": "tester", "role": "user"}


async def _fake_admin():
    return {"user_id": 1, "user_name": "admin", "role": "admin"}


def _build_app() -> FastAPI:
    portal = APIRouter()
    portal.include_router(personal_skills.router, prefix="/skills/personal")
    portal.include_router(skills.router, prefix="/skills")
    app = FastAPI()
    app.dependency_overrides[require_api_key] = _fake_user
    app.include_router(portal, prefix="/api/portal")
    return app


def test_personal_publication_submit_route_exists():
    routes = {route.path for route in _build_app().routes if hasattr(route, "path")}
    assert "/api/portal/skills/personal/{skill_id}/publication-requests" in routes
    assert "/api/portal/skills/personal/{skill_id}/publication-requests/withdraw" in routes


def test_admin_publication_review_routes_exist():
    routes = {route.path for route in _build_app().routes if hasattr(route, "path")}
    assert "/api/portal/skills/publication-requests" in routes
    assert "/api/portal/skills/publication-requests/{version_id}/approve" in routes
    assert "/api/portal/skills/publication-requests/{version_id}/reject" in routes


def test_personal_submit_returns_publication_summary(monkeypatch):
    expected = {
        "publication_id": "publication-1",
        "version_id": "version-1",
        "publication_status": "PENDING",
        "version_number": 1,
    }
    monkeypatch.setattr(
        "app.api.portal.endpoints.personal_skills.submit_personal_skill",
        AsyncMock(return_value=expected),
    )

    response = TestClient(_build_app()).post(
        "/api/portal/skills/personal/demo/publication-requests"
    )

    assert response.status_code == 200
    assert response.json()["data"] == expected


def test_personal_withdraw_returns_publication_summary(monkeypatch):
    expected = {
        "publication_id": "publication-1",
        "version_id": "version-1",
        "publication_status": "WITHDRAWN",
        "version_status": "WITHDRAWN",
    }
    monkeypatch.setattr(
        "app.api.portal.endpoints.personal_skills.withdraw_personal_skill_publication",
        AsyncMock(return_value=expected),
    )

    response = TestClient(_build_app()).post(
        "/api/portal/skills/personal/demo/publication-requests/withdraw"
    )

    assert response.status_code == 200
    assert response.json()["data"] == expected


def test_reject_requires_non_blank_comment():
    app = _build_app()
    app.dependency_overrides[skills.skill_publication_reviewer] = _fake_admin
    with patch(
        "app.api.portal.endpoints.skills.reject_publication",
        new=AsyncMock(side_effect=ValueError("reject comment is required")),
    ):
        response = TestClient(app).post(
            "/api/portal/skills/publication-requests/version-1/reject",
            json={"comment": "   "},
        )
    assert response.status_code in {400, 422}
