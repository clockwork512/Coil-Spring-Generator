"""Compression spring calculations.

All internal values are SI-ish: millimetres, newtons, megapascals (N/mm^2).
Formulas follow Shigley's Mechanical Engineering Design, ch. 10.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# Materials
# G in MPa, E in MPa, density in kg/m^3.
# Ultimate tensile strength Sut = A / d^m  (d in mm, Sut in MPa)
# allow = fraction of Sut allowed as torsional stress at solid (set removed),
# Shigley Table 10-6.
# ---------------------------------------------------------------------------
MATERIALS = {
    "Music wire (ASTM A228)":          dict(G=81_700, E=203_400, rho=7850, A=2211, m=0.145, allow=0.45),
    "Hard-drawn (ASTM A227)":          dict(G=80_700, E=197_900, rho=7850, A=1783, m=0.190, allow=0.45),
    "Oil-tempered (ASTM A229)":        dict(G=77_200, E=196_500, rho=7850, A=1855, m=0.187, allow=0.50),
    "Chrome-vanadium (ASTM A232)":     dict(G=77_200, E=203_400, rho=7850, A=2005, m=0.168, allow=0.50),
    "Chrome-silicon (ASTM A401)":      dict(G=77_200, E=203_400, rho=7850, A=1974, m=0.108, allow=0.50),
    "Stainless 302 (ASTM A313)":       dict(G=69_000, E=193_000, rho=7920, A=1867, m=0.146, allow=0.35),
    "17-7 PH stainless (A313 631, CH900)": dict(G=75_800, E=203_400, rho=7810, A=2023, m=0.092, allow=0.45),
    "Phosphor bronze (ASTM B159)":     dict(G=41_400, E=103_400, rho=8860, A=932,  m=0.064, allow=0.35),
}

END_TYPES = ["Open", "Open & ground", "Closed", "Closed & ground"]

# Number of inactive coils added to active coils for each end type
_END_COILS = {"Open": 0, "Open & ground": 1, "Closed": 2, "Closed & ground": 2}

MM_PER_IN = 25.4
N_PER_LBF = 4.448221615
MPA_PER_KSI = 6.894757


@dataclass
class SpringInput:
    wire_d: float = 2.0          # mm
    mean_d: float = 18.0         # mm  (OD = mean + d, ID = mean - d)
    active_coils: float = 8.0
    free_length: float = 50.0    # mm
    end_type: str = "Closed & ground"
    material: str = "Music wire (ASTM A228)"
    right_hand: bool = True
    work_length: float | None = None  # optional operating length, mm

    @property
    def od(self) -> float:
        return self.mean_d + self.wire_d

    @property
    def id(self) -> float:
        return self.mean_d - self.wire_d

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SpringResult:
    rate: float = 0.0            # N/mm
    index: float = 0.0           # C = D/d
    total_coils: float = 0.0
    pitch: float = 0.0           # active pitch, mm
    solid_length: float = 0.0
    max_deflection: float = 0.0  # free -> solid
    force_solid: float = 0.0
    wahl: float = 0.0
    bergstrasser: float = 0.0
    stress_solid: float = 0.0    # MPa (Bergstrasser-corrected)
    sut: float = 0.0
    allow: float = 0.0           # allowable torsional stress at solid
    safety_solid: float = 0.0
    pitch_angle_deg: float = 0.0
    slenderness: float = 0.0     # L0 / D
    buckling_limit: float = 0.0  # L0/D limit for stability (flat parallel ends)
    nat_freq: float = 0.0        # Hz, both ends on flat plates
    wire_length: float = 0.0     # mm
    mass: float = 0.0            # g
    od_solid: float = 0.0        # OD growth at solid
    work_deflection: float | None = None
    work_force: float | None = None
    work_stress: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def material_props(name: str) -> dict:
    return MATERIALS[name]


def end_geometry(end_type: str, d: float, na: float, p: float):
    """Return (total coils, free length, solid length) for an end type."""
    if end_type == "Open":
        nt = na
        l0 = p * na + d
        ls = d * (nt + 1)
    elif end_type == "Open & ground":
        nt = na + 1
        l0 = p * (na + 1)
        ls = d * nt
    elif end_type == "Closed":
        nt = na + 2
        l0 = p * na + 3 * d
        ls = d * (nt + 1)
    elif end_type == "Closed & ground":
        nt = na + 2
        l0 = p * na + 2 * d
        ls = d * nt
    else:
        raise ValueError(end_type)
    return nt, l0, ls


def pitch_from_free_length(end_type: str, d: float, na: float, l0: float) -> float:
    if end_type == "Open":
        return (l0 - d) / na
    if end_type == "Open & ground":
        return l0 / (na + 1)
    if end_type == "Closed":
        return (l0 - 3 * d) / na
    if end_type == "Closed & ground":
        return (l0 - 2 * d) / na
    raise ValueError(end_type)


def spring_rate(G: float, d: float, D: float, na: float) -> float:
    """k = G d^4 / (8 D^3 Na)   [N/mm]"""
    return G * d**4 / (8 * D**3 * na)


def active_coils_for_rate(G: float, d: float, D: float, k: float) -> float:
    return G * d**4 / (8 * D**3 * k)


def wire_d_for_rate(G: float, D: float, na: float, k: float) -> float:
    return (8 * D**3 * na * k / G) ** 0.25


def compute(s: SpringInput) -> SpringResult:
    r = SpringResult()
    d, D, na, l0 = s.wire_d, s.mean_d, s.active_coils, s.free_length

    if d <= 0:
        r.errors.append("Wire diameter must be positive.")
    if D <= d:
        r.errors.append("Mean diameter must be larger than the wire diameter (ID must be > 0).")
    if na <= 0:
        r.errors.append("Active coils must be positive.")
    if l0 <= 0:
        r.errors.append("Free length must be positive.")
    if r.errors:
        return r

    mat = material_props(s.material)
    G, rho = mat["G"], mat["rho"]

    C = D / d
    k = spring_rate(G, d, D, na)
    p = pitch_from_free_length(s.end_type, d, na, l0)
    nt, _, ls = end_geometry(s.end_type, d, na, p)

    r.index = C
    r.rate = k
    r.pitch = p
    r.total_coils = nt
    r.solid_length = ls
    r.max_deflection = l0 - ls
    r.force_solid = k * r.max_deflection

    r.wahl = (4 * C - 1) / (4 * C - 4) + 0.615 / C if C > 1 else float("nan")
    r.bergstrasser = (4 * C + 2) / (4 * C - 3)
    r.stress_solid = r.bergstrasser * 8 * r.force_solid * D / (math.pi * d**3)
    r.sut = mat["A"] / d ** mat["m"]
    r.allow = mat["allow"] * r.sut
    r.safety_solid = r.allow / r.stress_solid if r.stress_solid > 0 else float("inf")

    r.pitch_angle_deg = math.degrees(math.atan(p / (math.pi * D)))
    r.slenderness = l0 / D
    # Absolute stability for steel with flat parallel (ground/closed) ends: L0 < 2.63 D / alpha, alpha = 0.5
    # End condition constant: ground ends ~ fixed, closed unground ~ fixed/pinned, open ~ pinned
    alpha = {"Open": 1.0, "Closed": 0.707}.get(s.end_type, 0.5)
    r.buckling_limit = 2.63 / alpha

    # Natural frequency, both ends against flat plates: f = (d / (2 pi Na D^2)) sqrt(G / (2 rho))
    G_pa = G * 1e6
    d_m, D_m = d / 1000, D / 1000
    r.nat_freq = d_m / (2 * math.pi * na * D_m**2) * math.sqrt(G_pa / (2 * rho))

    r.wire_length = math.sqrt((math.pi * D) ** 2 + p**2) * na + math.pi * D * (nt - na)
    r.mass = rho * (math.pi * (d / 1000) ** 2 / 4) * (r.wire_length / 1000) * 1000  # grams

    # OD at solid (coils open up slightly as pitch angle -> 0)
    r.od_solid = math.sqrt(D**2 + (p**2 - d**2) / math.pi**2) + d

    if s.work_length is not None:
        dx = l0 - s.work_length
        r.work_deflection = dx
        r.work_force = k * dx
        r.work_stress = r.bergstrasser * 8 * r.work_force * D / (math.pi * d**3)
        if s.work_length < ls:
            r.warnings.append("Working length is below solid height.")

    # ---- Checks -----------------------------------------------------------
    if p <= d:
        r.errors.append(
            f"Free length is too short: active pitch ({p:.3f} mm) must exceed the wire "
            f"diameter ({d:.3f} mm). Increase free length or reduce coils."
        )
    if C < 4:
        r.warnings.append(f"Spring index C = {C:.2f} is below 4 – hard to coil, high stress.")
    elif C > 16:
        r.warnings.append(f"Spring index C = {C:.2f} is above 16 – prone to tangling and buckling.")
    if r.safety_solid < 1.0:
        r.warnings.append(
            f"Stress at solid ({r.stress_solid:.0f} MPa) exceeds the allowable "
            f"{r.allow:.0f} MPa – spring will take a set if compressed solid."
        )
    if r.slenderness > r.buckling_limit:
        r.warnings.append(
            f"L0/D = {r.slenderness:.2f} exceeds {r.buckling_limit:.2f} – may buckle; "
            "guide on a rod or in a bore."
        )
    if r.pitch_angle_deg > 12:
        r.warnings.append(f"Pitch angle {r.pitch_angle_deg:.1f}° is large; rate formula loses accuracy.")
    if na < 3:
        r.warnings.append("Fewer than 3 active coils – rate will be inaccurate.")
    return r
