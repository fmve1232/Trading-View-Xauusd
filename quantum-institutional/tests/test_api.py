"""API surface. Sections 46, 68, 83."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from quantum_institutional.api.app import PENDING_ROUTES, create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


class TestImplementedEndpoints:
    def test_health_is_liveness_only(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_version_exposes_the_full_section_57_identity(self, client: TestClient) -> None:
        body = client.get("/version").json()
        assert set(body) == {
            "engine_version",
            "formula_registry_version",
            "schema_version",
            "git_commit",
            "reproducible",
        }

    def test_system_status_reports_components_not_a_blanket_ok(self, client: TestClient) -> None:
        body = client.get("/system-status").json()
        assert body["overall"] == "OFFLINE"
        assert body["signals_permitted"] is False
        assert {c["component"] for c in body["components"]} >= {"market_data", "database", "model"}
        assert all(c["detail"].startswith("not implemented") for c in body["components"])


class TestPendingEndpoints:
    @pytest.mark.parametrize("path", sorted(PENDING_ROUTES))
    def test_every_declared_route_returns_503_data_unavailable(self, client: TestClient, path: str) -> None:
        """Never a plausible payload, and never a 404 a client would cache."""
        response = client.get(path)
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "DATA_UNAVAILABLE"
        assert body["path"] == path
        assert "Phase" in body["reason"]

    def test_each_route_reports_its_own_reason(self, client: TestClient) -> None:
        """Guards the closure bug where every route reports the last one's reason."""
        assert client.get("/bars").json()["reason"] != client.get("/risk").json()["reason"]

    def test_the_section_46_route_list_is_complete(self, client: TestClient) -> None:
        declared = {route.path for route in create_app().routes}
        required = set(PENDING_ROUTES) | {"/health", "/version", "/system-status"}
        assert required <= declared
