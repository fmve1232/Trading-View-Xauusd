"""FastAPI surface. Master prompt sections 46, 47, 68 and 83.

THREE ENDPOINTS ARE REAL. THE REST ARE HONEST 503s.
---------------------------------------------------
``/health``, ``/version`` and ``/system-status`` compute their answers now.
Every data endpoint in section 46 is declared, documented and returns
``503 DATA_UNAVAILABLE`` with the phase that will implement it.

Declaring them as 503 rather than omitting them is the point: the dashboard and
the API contract can be built against the real route list, and no consumer can
ever receive a plausible-looking fabricated payload (section 83). A route that
starts returning data does so because an engine was wired up, not because a
placeholder was left in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..monitoring.health import collect_health
from ..version import current_stamp

__all__ = ["app", "create_app"]

#: Section 46 route list, mapped to the phase that implements each one.
PENDING_ROUTES: dict[str, str] = {
    "/market": "Phase 15 -- live data pipeline",
    "/bars": "Phase 3 -- historical ingestion",
    "/features": "Phase 5 -- feature store",
    "/smc": "Phase 7 -- SMC engine",
    "/regime": "Phase 8 -- regime engine",
    "/macro": "Phase 14 -- macro pipeline",
    "/news": "Phase 14 -- news pipeline",
    "/probability": "Phase 9 -- probability engine",
    "/signals": "Phase 11 -- signal engine",
    "/risk": "Phase 16 -- risk engine",
    "/performance": "Phase 11 -- backtest engine",
    "/models": "Phase 13 -- ML pipeline",
    "/audit": "Phase 18 -- audit log store",
    "/trace": "Phase 18 -- end-to-end trace (section 47)",
}


def _unavailable(path: str, reason: str) -> JSONResponse:
    """The single shape every not-yet-real endpoint returns.

    HTTP 503 rather than 404 or 501: the resource is legitimate and temporarily
    unserveable. A 404 would tell a client the route does not exist, and a
    client that caches that will not come back when the engine lands.
    """
    return JSONResponse(
        status_code=503,
        content={
            "status": "DATA_UNAVAILABLE",
            "path": path,
            "reason": reason,
            "checked_at": datetime.now(UTC).isoformat(),
        },
    )


def create_app() -> FastAPI:
    application = FastAPI(
        title="Quantum Institutional API",
        version=current_stamp().engine_version,
        description=(
            "XAUUSD quantitative research platform. Quantum 5.0 (Pine v6) is the "
            "reference layer. Endpoints that are not yet backed by a validated "
            "engine return 503 DATA_UNAVAILABLE rather than placeholder data."
        ),
    )

    @application.get("/health", tags=["system"])
    def health() -> dict[str, Any]:
        """Liveness. Answers "is the process up", not "is the data good"."""
        return {"status": "ok", "checked_at": datetime.now(UTC).isoformat()}

    @application.get("/version", tags=["system"])
    def version() -> dict[str, Any]:
        """Section 57: the identity every production result must carry."""
        stamp = current_stamp()
        return {
            "engine_version": stamp.engine_version,
            "formula_registry_version": stamp.formula_registry_version,
            "schema_version": stamp.schema_version,
            "git_commit": stamp.git_commit,
            "reproducible": stamp.is_reproducible,
        }

    @application.get("/system-status", tags=["system"])
    def system_status() -> dict[str, Any]:
        """Section 54: per-component health, and whether signals are permitted."""
        snapshot = collect_health()
        return {
            "checked_at": snapshot.checked_at.isoformat(),
            "overall": snapshot.overall.value,
            "signals_permitted": snapshot.signals_permitted,
            "git_commit": snapshot.stamp.git_commit,
            "components": [
                {
                    "component": component.component,
                    "quality": component.quality.value,
                    "detail": component.detail,
                    "last_update": component.last_update.isoformat() if component.last_update else None,
                }
                for component in snapshot.components
            ],
        }

    for path, reason in PENDING_ROUTES.items():
        _register_pending(application, path, reason)

    return application


def _register_pending(application: FastAPI, path: str, reason: str) -> None:
    """Attach one 503 route.

    Kept in a helper so each closure captures its own ``path`` and ``reason``;
    defining them inside the loop body would have every route report the last
    entry's reason.
    """

    async def handler() -> JSONResponse:
        return _unavailable(path, reason)

    handler.__name__ = f"pending_{path.strip('/').replace('/', '_')}"
    application.add_api_route(
        path,
        handler,
        methods=["GET"],
        tags=["pending"],
        summary=f"Not yet implemented -- {reason}",
        status_code=503,
    )


app = create_app()
