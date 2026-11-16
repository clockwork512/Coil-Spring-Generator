"""Coil Spring Designer – web server.

Serves the browser front end (static/) and a small JSON API that reuses the
desktop app's calculation (calc.py, clamp.py) and CAD (geometry.py) code.
All API values are in mm, N and MPa; the browser converts for display.

Start it with run_web.py (or run_web_windows.bat) from the project folder.
"""
from __future__ import annotations

import math
import os
import tempfile
import threading
from dataclasses import asdict
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..calc import (
    MATERIALS, END_TYPES, DEFAULT_MATERIAL, SpringInput, compute, wire_chart,
    active_coils_for_rate, wire_d_for_rate,
)
from ..clamp import ClampInput, compute_clamp, pressure_curve, METHODS
from ..geometry import tube_mesh, centerline
from .. import trace as trace_mod

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Shown in the page's toolbar and printed by run_web.py.  Bump it when the site changes;
# it is also added to the page's file links so browsers never keep an old copy.
WEB_VERSION = "1.3"
_cad_lock = threading.Lock()          # OpenCASCADE: build one solid at a time

app = FastAPI(title="Coil Spring Designer", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Request models (mm / N / MPa).  Bounds keep one request from tying up the PC.
# ---------------------------------------------------------------------------
class Spring(BaseModel):
    wire_d: float = Field(gt=0, le=100)
    mean_d: float = Field(gt=0, le=2000)
    active_coils: float = Field(ge=0.5, le=200)
    free_length: float = Field(gt=0, le=10000)
    end_type: Literal["Open", "Open & ground", "Closed", "Closed & ground"] = "Closed & ground"
    material: str = DEFAULT_MATERIAL
    right_hand: bool = True
    work_length: Optional[float] = Field(default=None, ge=0, le=10000)

    def to_input(self) -> SpringInput:
        if self.material not in MATERIALS:
            raise HTTPException(400, f"Unknown material: {self.material}")
        return SpringInput(**self.model_dump())


class Target(BaseModel):
    mode: Literal["rate", "force"] = "rate"
    rate: float = Field(default=1.0, gt=0)                 # N/mm
    force: float = Field(default=1.0, gt=0)                # N
    distance: float = Field(default=1.0, gt=0)             # mm
    distance_kind: Literal["deflection", "length"] = "deflection"


class SolveRequest(BaseModel):
    spring: Spring
    target: Target
    solve: Literal["coils", "wire"]
    dia_mode: Literal["od", "id", "mean"] = "od"
    snap: bool = True


class ClampRequest(BaseModel):
    source: Literal["design", "catalog"] = "catalog"
    spring: Optional[Spring] = None                       # used when source == "design"
    rate: float = Field(default=52.0, gt=0)               # N/mm, catalog
    free_length: float = Field(default=17.0, gt=0)
    solid_length: float = Field(default=9.17, ge=0)
    n_springs: int = Field(default=8, ge=1, le=1000)
    displacement: float = Field(default=4.5, gt=0)
    disp_tol: float = Field(default=0.35, ge=0)
    rate_tol: float = Field(default=0.10, ge=0, le=1)
    area: float = Field(default=6000.0, gt=0)              # mm^2
    method: int = Field(default=0, ge=0, le=1)


# ---------------------------------------------------------------------------
def _round(v, n=5):
    if isinstance(v, float):
        return round(v, n) if math.isfinite(v) else None
    return v


def _result_dict(r) -> dict:
    d = {k: _round(v) for k, v in asdict(r).items()}
    d["ok"] = r.ok
    return d


@app.middleware("http")
async def no_stale_files(request, call_next):
    """Make browsers check for a newer page / script every time instead of using an old copy."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/")
def index():
    with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
        page = fh.read()
    page = (page.replace("/static/style.css", f"/static/style.css?v={WEB_VERSION}")
                .replace("/static/app.js", f"/static/app.js?v={WEB_VERSION}")
                .replace("{{VERSION}}", WEB_VERSION))
    return HTMLResponse(page)


@app.get("/api/meta")
def meta():
    mats = []
    for name, m in MATERIALS.items():
        mats.append(dict(name=name, G=m["G"], E=m.get("E"), allow=m["allow"],
                         chart=[dict(d=round(d, 5), sut=_round(s, 2)) for d, s in wire_chart(name)]))
    default = SpringInput(wire_d=0.080 * 25.4, mean_d=(0.750 - 0.080) * 25.4,
                          active_coils=8, free_length=2.0 * 25.4)
    return dict(version=WEB_VERSION, materials=mats, end_types=END_TYPES, methods=METHODS,
                default_spring=asdict(default), default_clamp=asdict(ClampInput()))


@app.post("/api/compute")
def api_compute(spring: Spring):
    s = spring.to_input()
    r = compute(s)
    out = dict(result=_result_dict(r), od=s.od, id=s.id)
    if r.ok:
        out["f_allow"] = r.allow * math.pi * s.wire_d ** 3 / (r.bergstrasser * 8 * s.mean_d)
        pts, *_ = centerline(s, 48)
        out["centerline"] = [[round(float(x), 4), round(float(y), 4), round(float(z), 4)]
                             for x, y, z in pts]
    return out


@app.post("/api/mesh")
def api_mesh(spring: Spring):
    s = spring.to_input()
    if not compute(s).ok:
        raise HTTPException(400, "Spring is not valid")
    verts, faces, normals = tube_mesh(s)
    return dict(verts=[round(float(v), 4) for v in verts.ravel()],
                normals=[round(float(v), 3) for v in normals.ravel()],
                faces=[int(i) for i in faces.ravel()])


@app.post("/api/solve")
def api_solve(req: SolveRequest):
    s = req.spring.to_input()
    t = req.target
    G = MATERIALS[s.material]["G"]
    x = None
    if t.mode == "rate":
        k = t.rate
    else:
        x = t.distance if t.distance_kind == "deflection" else s.free_length - t.distance
        if x <= 0:
            raise HTTPException(400, "Compressed length must be shorter than the free length.")
        k = t.force / x

    out = dict(target_rate=k)
    if req.solve == "coils":
        na = active_coils_for_rate(G, s.wire_d, s.mean_d, k)
        s.active_coils = max(0.5, round(na * 4) / 4)        # quarter turns
        out.update(exact=na, chosen=s.active_coils)
    else:
        d = s.wire_d
        for _ in range(60):     # keep the diameter the user set by (OD / ID / mean) fixed
            D = (s.mean_d if req.dia_mode == "mean" else
                 s.od - d if req.dia_mode == "od" else s.id + d)
            d_new = wire_d_for_rate(G, D, s.active_coils, k)
            if abs(d_new - d) < 1e-9:
                break
            d = d_new
        exact = d
        chart = [dc for dc, _ in wire_chart(s.material)]
        snapped = req.snap and bool(chart)
        if snapped:
            d = min(chart, key=lambda dc: abs(dc - exact))
            out["outside_chart"] = exact < chart[0] * 0.98 or exact > chart[-1] * 1.02
        od, idd = s.od, s.id
        s.mean_d = (s.mean_d if req.dia_mode == "mean" else od - d if req.dia_mode == "od" else idd + d)
        s.wire_d = d
        out.update(exact=exact, chosen=d, snapped=snapped)

    if x is not None:
        s.work_length = s.free_length - x
        r = compute(s)
        if r.ok:
            out.update(achieved_force=r.rate * x, target_force=t.force, deflection=x)
    out["spring"] = asdict(s)
    return out


@app.post("/api/clamp")
def api_clamp(req: ClampRequest):
    sres = None
    if req.source == "design":
        if req.spring is None:
            raise HTTPException(400, "No spring design given")
        s = req.spring.to_input()
        sres = compute(s)
        if not sres.rate or not sres.ok:
            raise HTTPException(400, "The spring design isn't valid – fix it on the Spring design page.")
        rate, free, solid = sres.rate, s.free_length, sres.solid_length
    else:
        rate, free, solid = req.rate, req.free_length, req.solid_length
    c = ClampInput(rate=rate, n_springs=req.n_springs, free_length=free, solid_length=solid,
                   displacement=req.displacement, disp_tol=req.disp_tol, rate_tol=req.rate_tol,
                   area=req.area, method=req.method)
    r = compute_clamp(c)
    out = dict(input=asdict(c), result=_result_dict(r))
    if r.force_total > 0:
        x, nom, lo, hi = pressure_curve(c)
        out["curve"] = dict(x=[round(float(v), 5) for v in x], nominal=[round(float(v), 6) for v in nom],
                            low=[round(float(v), 6) for v in lo], high=[round(float(v), 6) for v in hi])
    if sres is not None and sres.allow and r.force_total > 0:
        k = sres.bergstrasser * 8 * s.mean_d / (math.pi * s.wire_d ** 3)
        out["wire_stress"] = dict(high=k * r.force_high / c.n_springs, nominal=k * r.force_spring,
                                  allow=sres.allow)
    return out


class TraceRequest(BaseModel):
    spring: Spring
    dia_mode: Literal["od", "id", "mean"] = "od"
    clamp: Optional[ClampRequest] = None


@app.post("/api/trace")
def api_trace(req: TraceRequest):
    """Developer mode: every variable with its formula, values, links and source line."""
    s = req.spring.to_input()
    r = compute(s)
    t = trace_mod.trace_spring(s, r, ["od", "id", "mean"].index(req.dia_mode), ui="web")
    k = req.clamp
    if k is not None:
        design = k.source == "design"
        sres = r if design else None
        if design and not (r.ok and r.rate):
            k = None
        if k is not None:
            rate, free, solid = (r.rate, s.free_length, r.solid_length) if design else (k.rate, k.free_length, k.solid_length)
            c = ClampInput(rate=rate, n_springs=k.n_springs, free_length=free, solid_length=solid,
                           displacement=k.displacement, disp_tol=k.disp_tol, rate_tol=k.rate_tol,
                           area=k.area, method=k.method)
            trace_mod.trace_clamp(t, c, compute_clamp(c), design, s if design else None, sres)
    t.finish()
    out = []
    for v in t:
        val = v.value if isinstance(v.value, str) else _round(float(v.value), 10)
        out.append(dict(key=v.key, symbol=v.symbol, name=v.name, kind=v.kind, unit=v.unit, value=val,
                        formula=v.formula, subst=v.subst, deps=v.deps, used_by=v.used_by, group=v.group,
                        sources=[list(x) for x in v.sources], check=_round(v.check, 10) if isinstance(v.check, float) else v.check,
                        check_label=v.check_label, matches=v.matches, note=v.note))
    return dict(vars=out)


@app.post("/api/export/{fmt}")
def api_export(fmt: Literal["step", "stl"], spring: Spring):
    from .. import geometry
    s = spring.to_input()
    if not compute(s).ok:
        raise HTTPException(400, "Spring is not valid")
    fd, path = tempfile.mkstemp(suffix="." + fmt)
    os.close(fd)
    try:
        with _cad_lock:
            (geometry.export_step if fmt == "step" else geometry.export_stl)(s, path)
        with open(path, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    media = "application/step" if fmt == "step" else "model/stl"
    return Response(content=data, media_type=media)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
