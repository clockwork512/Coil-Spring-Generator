"""Spring centreline / mesh / CAD geometry.

The centreline is a helix whose pitch varies along its length so that
closed ends have tightly wound end turns that blend smoothly into the
active coils.  Ground ends are produced by cutting the swept solid flat
at z = 0 and z = free length.
"""
from __future__ import annotations

import math

import numpy as np

from .calc import SpringInput, end_geometry, pitch_from_free_length

SAMPLES_PER_TURN = 36


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def centerline(s: SpringInput, samples_per_turn: int = SAMPLES_PER_TURN, end_gap: float = 0.0):
    """Return (points Nx3, total_coils, z_start, rise).

    end_gap: extra clearance added to closed-end pitch (as a fraction of d)
    so that adjacent touching coils don't produce a degenerate solid in CAD.
    """
    d, D, na, l0 = s.wire_d, s.mean_d, s.active_coils, s.free_length
    p = pitch_from_free_length(s.end_type, d, na, l0)
    nt, _, _ = end_geometry(s.end_type, d, na, p)
    ground = "ground" in s.end_type
    closed = s.end_type.startswith("Closed")

    z_start = 0.0 if ground else d / 2
    rise = l0 - (0.0 if ground else d)        # centreline rise from first to last point
    end_turns = (nt - na) / 2 if closed else 0.0
    p_end = d * (1 + end_gap)
    p_act = (rise - 2 * end_turns * p_end) / na if closed else rise / nt

    n = max(int(math.ceil(nt * samples_per_turn)), 16)
    t = np.linspace(0.0, nt, n + 1)               # turns

    if closed:
        # pitch(t): p_end in the end turns, p_act in the middle, smooth blend
        w = min(0.5, end_turns * 0.8, na * 0.4)    # blend width, turns
        a = _smoothstep((t - (end_turns - w / 2)) / w)
        b = _smoothstep(((nt - end_turns) + w / 2 - t) / w)
        pitch = p_end + (p_act - p_end) * np.minimum(a, b)
        # integrate (trapezoid) and rescale so the total rise is exact
        z = np.concatenate([[0.0], np.cumsum(0.5 * (pitch[1:] + pitch[:-1]) * np.diff(t))])
        z *= rise / z[-1]
    else:
        z = t * p_act
    z += z_start

    ang = 2 * math.pi * t * (1 if s.right_hand else -1)
    r = D / 2
    pts = np.column_stack([r * np.cos(ang), r * np.sin(ang), z])
    return pts, nt, z_start, rise


# ---------------------------------------------------------------------------
# Fast tube mesh for the preview (no CAD kernel needed)
# ---------------------------------------------------------------------------
def tube_mesh(s: SpringInput, sides: int = 14, samples_per_turn: int = 40):
    pts, *_ = centerline(s, samples_per_turn)
    rad = s.wire_d / 2
    n = len(pts)

    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    # Use the radial direction (towards the axis) to build a stable frame
    radial = np.column_stack([pts[:, 0], pts[:, 1], np.zeros(n)])
    radial /= np.linalg.norm(radial, axis=1, keepdims=True)
    nrm = radial - (radial * tang).sum(1, keepdims=True) * tang
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    bin_ = np.cross(tang, nrm)

    th = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = np.cos(th)[None, :, None] * nrm[:, None, :] + np.sin(th)[None, :, None] * bin_[:, None, :]
    verts = pts[:, None, :] + rad * ring          # n x sides x 3
    normals = ring.copy()

    if "ground" in s.end_type:
        z = verts[..., 2]
        lo, hi = z < 0, z > s.free_length
        verts[..., 2] = np.clip(z, 0, s.free_length)
        normals[lo] = (0, 0, -1)
        normals[hi] = (0, 0, 1)

    verts = verts.reshape(-1, 3)
    normals = normals.reshape(-1, 3)

    i = np.arange(n - 1)[:, None]
    j = np.arange(sides)[None, :]
    a = i * sides + j
    b = i * sides + (j + 1) % sides
    c = a + sides
    e = b + sides
    faces = np.concatenate([np.stack([a, b, e], -1).reshape(-1, 3),
                            np.stack([a, e, c], -1).reshape(-1, 3)])
    # end caps
    for k in (0, n - 1):
        center_idx = len(verts)
        verts = np.vstack([verts, pts[k]])
        normals = np.vstack([normals, -tang[k] if k == 0 else tang[k]])
        base = k * sides
        cap = np.array([[center_idx, base + (q + 1) % sides, base + q] for q in range(sides)])
        if k == n - 1:
            cap = cap[:, [0, 2, 1]]
        faces = np.vstack([faces, cap])
    return verts.astype(np.float32), faces.astype(np.int32), normals.astype(np.float32)


# ---------------------------------------------------------------------------
# CAD solid (CadQuery / OpenCASCADE)
# ---------------------------------------------------------------------------
def build_solid(s: SpringInput):
    import cadquery as cq

    # A small clearance on the closed-end pitch keeps touching coils from
    # producing a self-intersecting solid.  0.5% of d is far below any
    # manufacturing tolerance.
    pts, nt, z_start, rise = centerline(s, samples_per_turn=24, end_gap=0.005)
    vecs = [cq.Vector(*map(float, p)) for p in pts]
    path = cq.Wire.assembleEdges([cq.Edge.makeSpline(vecs)])

    t0 = (pts[1] - pts[0])
    t0 /= np.linalg.norm(t0)
    circle = cq.Wire.makeCircle(s.wire_d / 2, cq.Vector(*map(float, pts[0])), cq.Vector(*map(float, t0)))
    solid = cq.Solid.sweep(circle, [], path, makeSolid=True, isFrenet=True)

    if "ground" in s.end_type:
        big = s.mean_d * 3 + s.wire_d * 4
        box = cq.Solid.makeBox(big, big, s.free_length,
                               pnt=cq.Vector(-big / 2, -big / 2, 0))
        solid = solid.intersect(box)
        # intersect returns a Compound; pull out the solid
        solids = solid.Solids()
        if len(solids) == 1:
            solid = solids[0]
    return solid


def export_step(s: SpringInput, path: str):
    import cadquery as cq
    solid = build_solid(s)
    cq.exporters.export(cq.Workplane().add(solid), path, exportType="STEP")
    return solid


def export_stl(s: SpringInput, path: str, tolerance: float = 0.02):
    import cadquery as cq
    solid = build_solid(s)
    cq.exporters.export(cq.Workplane().add(solid), path, exportType="STL",
                        tolerance=tolerance * s.wire_d, angularTolerance=0.1)
    return solid
