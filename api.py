"""FastAPI geometry service for the 3-D navigator."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ephemeris import (
    MAX_SUPPORTED_DATE,
    MIN_SUPPORTED_DATE,
    EphemerisDataError,
    GeometryInputError,
    LunarGeometry,
    build_hourly_utc_grid,
)
from sites import get_site_list

app = FastAPI(title="Lunar Navigator Geometry")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

KERNEL_DIR = Path(os.environ.get("LUNAR_NAVIGATOR_KERNEL_DIR", Path(__file__).parent / "data" / "kernels"))


class WindowRequest(BaseModel):
    site_ids: list[str]
    start: date
    end: date


@app.get("/sites")
def list_sites():
    return [
        {
            "site_id": s.site_id,
            "name": s.name,
            "latitude_deg": s.latitude_deg,
            "longitude_deg": s.longitude_deg,
        }
        for s in get_site_list()
    ]


@app.post("/geometry")
def geometry(req: WindowRequest):
    if not req.site_ids:
        raise HTTPException(400, "At least one site_id is required.")
    try:
        timestamps = build_hourly_utc_grid(req.start, req.end)
    except GeometryInputError as exc:
        raise HTTPException(400, str(exc)) from exc

    geometry_engine = None
    try:
        geometry_engine = LunarGeometry(KERNEL_DIR)
        sites = {s.site_id: s for s in get_site_list()}
        out = []
        for sid in req.site_ids:
            if sid not in sites:
                raise HTTPException(404, f"Unknown site_id: {sid}")
            result = geometry_engine.calculate_site(sites[sid], timestamps)
            out.append(
                {
                    "site_id": sid,
                    "name": result.site.name,
                    "timestamps_utc": [t.isoformat() for t in result.timestamps_utc],
                    "sun_elevation_deg": result.sun_elevation_deg,
                    "sun_azimuth_deg": result.sun_azimuth_deg,
                    "earth_elevation_deg": result.earth_elevation_deg,
                    "earth_azimuth_deg": result.earth_azimuth_deg,
                }
            )
        return {"samples": len(timestamps), "sites": out}
    except EphemerisDataError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        if geometry_engine is not None:
            geometry_engine.close()
