"""FastAPI application: JSON API plus the static dashboard."""

from __future__ import annotations

import hmac
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings, resolve_app_dir
from .models import Sample
from .service import PrecursorService, SimulatorRunner
from .vault import Vault, verify_bundle

log = logging.getLogger("precursor.api")

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'")


class IngestSample(BaseModel):
    t: Optional[float] = Field(None, description="Sample time in seconds. Server time if omitted.")
    values: dict[str, float] = Field(..., min_length=1)


class IngestBatch(BaseModel):
    samples: list[IngestSample] = Field(..., min_length=1, max_length=1000)


class InjectRequest(BaseModel):
    fault: str
    severity: float = Field(1.0, gt=0, le=3)


def create_app(settings: Settings, *, start_simulator: bool = True,
               db_path: Optional[str] = None) -> FastAPI:
    simulate = settings.server.mode == "simulate"
    vault = Vault(db_path or settings.server.db_path)
    service = PrecursorService(settings, vault, source="simulation" if simulate else "live")
    runner = SimulatorRunner(service, settings.server.sim_speed, settings.server.sim_seed,
                             settings.server.sim_auto_faults) if simulate else None
    app_dir = resolve_app_dir()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if runner and start_simulator:
            runner.start()
        yield
        if runner:
            runner.stop()
        service.close()

    app = FastAPI(title="Precursor", version=__version__, lifespan=lifespan,
                  description="Flight-data recorder for small machines.")
    app.state.service = service
    app.state.runner = runner

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def require_key(x_api_key: Optional[str] = Header(default=None)) -> None:
        expected = settings.server.api_key
        if expected and not hmac.compare_digest(x_api_key or "", expected):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")

    # ------------------------------------------------------------- pages
    if app_dir is not None:
        app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        if app_dir is None:
            return JSONResponse({"detail": "Dashboard files not found. Run from the "
                                 "repository root or set PRECURSOR_APP_DIR."}, status_code=404)
        return FileResponse(app_dir / "index.html")

    # --------------------------------------------------------------- api
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "mode": settings.server.mode}

    @app.get("/api/config")
    def config():
        d = settings.detection
        return {
            "machine": {"id": settings.machine_id, "name": settings.machine_name},
            "mode": settings.server.mode, "sim_speed": settings.server.sim_speed,
            "channels": [{"name": c.name, "label": c.label, "unit": c.unit}
                         for c in settings.channels],
            "faults": [{"name": f.name, "description": f.description}
                       for f in settings.faults.values()] if simulate else [],
            "detection": {"z_trigger": d.z_trigger, "pre_roll_s": d.pre_roll_s,
                          "post_roll_s": d.post_roll_s, "ring_capacity_s": d.ring_capacity_s,
                          "warmup_samples": d.warmup_samples},
            "ingest_requires_key": bool(settings.server.api_key),
        }

    @app.get("/api/live")
    def live(since: int = Query(0, ge=0), limit: int = Query(600, ge=1, le=1800)):
        return service.live(since, limit)

    @app.get("/api/incidents")
    def incidents():
        return {"incidents": vault.list()}

    @app.get("/api/incidents/{incident_id}")
    def incident(incident_id: str):
        bundle = vault.get(incident_id)
        if bundle is None:
            raise HTTPException(404, f"No incident {incident_id}")
        return bundle

    @app.get("/api/incidents/{incident_id}/bundle")
    def incident_bundle(incident_id: str):
        bundle = vault.get(incident_id)
        if bundle is None:
            raise HTTPException(404, f"No incident {incident_id}")
        ok, reason = verify_bundle(bundle)
        return JSONResponse(
            {**bundle, "self_check": {"ok": ok, "reason": reason}},
            headers={"Content-Disposition": f'attachment; filename="{incident_id}.json"'})

    @app.get("/api/vault/verify")
    def vault_verify():
        return vault.verify().to_dict()

    @app.post("/api/ingest", dependencies=[Depends(require_key)])
    def ingest(body: Union[IngestBatch, IngestSample]):
        if simulate:
            raise HTTPException(409, "Server is in simulate mode; external ingest is disabled. "
                                     "Start with --ingest (PRECURSOR_MODE=ingest) to accept data.")
        items = body.samples if isinstance(body, IngestBatch) else [body]
        accepted, incidents_sealed = 0, []
        for item in items:
            t = item.t if item.t is not None else time.time()
            result, incident_id = service.ingest(Sample(t=t, values=item.values))
            accepted += int(result.accepted)
            if incident_id:
                incidents_sealed.append(incident_id)
        return {"accepted": accepted, "dropped": len(items) - accepted,
                "incidents_sealed": incidents_sealed}

    @app.post("/api/sim/inject", dependencies=[Depends(require_key)])
    def sim_inject(body: InjectRequest):
        if runner is None:
            raise HTTPException(409, "Fault injection only exists in simulate mode.")
        if body.fault not in settings.faults:
            raise HTTPException(422, f"Unknown fault '{body.fault}'. "
                                     f"Known: {sorted(settings.faults)}")
        return runner.inject(body.fault, body.severity)

    return app
