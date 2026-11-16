"""Compression spring calculations.

All internal values are SI-ish: millimetres, newtons, megapascals (N/mm^2).
Formulas follow Shigley's Mechanical Engineering Design, ch. 10.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

MM_PER_IN = 25.4
N_PER_LBF = 4.448221615
MPA_PER_KSI = 6.894757

# ---------------------------------------------------------------------------
# Materials
#
#   G, E        shear and Young's modulus, MPa
#   rho         density, kg/m^3
#   allow       fraction of tensile strength allowed as stress at solid height
#   A, m        tensile strength formula  Sut = A / d^m  (d in mm, Sut in MPa).
#               Used for any wire size that has no tensile value in the chart.
#   chart_unit  "in" or "mm": the units the chart below is written in
#   chart       the wire sizes you can get for this material. Each entry is either
#                   0.080            diameter only (strength comes from A / d^m), or
#                   (0.080, 284)     diameter and minimum tensile strength
#                                    (ksi for an "in" chart, MPa for a "mm" chart).
#               These sizes fill the "Std..." dropdown and the snap-to-size solver.
#               If two or more sizes have a tensile value, the app interpolates
#               between them instead of using A / d^m.
# ---------------------------------------------------------------------------
MATERIALS = {
    "Music wire (ASTM A228)": dict(
        G=81_700, E=203_400, rho=7850, A=2211, m=0.145, allow=0.45,
        chart_unit="in",
        chart=[
            0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010, 0.011, 0.012, 0.013,
            0.014, 0.016, 0.018, 0.020, 0.022, 0.024, 0.026, 0.028, 0.029, 0.031,
            0.033, 0.035, 0.037, 0.039, 0.041, 0.043, 0.045, 0.047, 0.049, 0.051,
            0.055, 0.059, 0.063, 0.067, 0.071, 0.075, 0.080, 0.085, 0.090, 0.095,
            0.100, 0.106, 0.112, 0.118, 0.125, 0.135, 0.148, 0.162, 0.177, 0.192,
            0.207, 0.225, 0.250,
        ],
    ),
    "17-7 PH stainless (A313 631, CH900)": dict(
        G=75_800, E=203_400, rho=7810, A=2023, m=0.092, allow=0.45,
        chart_unit="in",
        chart=[
            0.010, 0.012, 0.014, 0.016, 0.018, 0.020, 0.022, 0.024, 0.026, 0.028,
            0.029, 0.031, 0.033, 0.035, 0.037, 0.039, 0.041, 0.043, 0.045, 0.047,
            0.049, 0.051, 0.055, 0.059, 0.063, 0.067, 0.071, 0.075, 0.080, 0.085,
            0.090, 0.095, 0.100, 0.106, 0.112, 0.118, 0.125, 0.135, 0.148, 0.162,
            0.177, 0.192, 0.207, 0.225, 0.250,
        ],
    ),
}

DEFAULT_MATERIAL = next(iter(MATERIALS))


def wire_chart(material: str):
    """The material's wire chart as a sorted list of (diameter mm, tensile MPa or None)."""
    mat = MATERIALS[material]
    inch = mat.get("chart_unit", "mm") == "in"
    out = []
    for entry in mat.get("chart", []):
        d, sut = entry if isinstance(entry, (tuple, list)) else (entry, None)
        d_mm = d * MM_PER_IN if inch else d
        sut_mpa = None if sut is None else (sut * MPA_PER_KSI if inch else sut)
        out.append((d_mm, sut_mpa))
    return sorted(out)


def in_chart(material: str, d: float) -> bool:
    """True if wire diameter d (mm) matches a chart size (within 0.1%)."""
    return any(abs(dc - d) <= 1e-3 * dc for dc, _ in wire_chart(material))


def tensile_strength(material: str, d: float):
    """(Sut in MPa, True if it came from the chart) for wire diameter d (mm)."""
    mat = MATERIALS[material]
    pts = [(dc, sc) for dc, sc in wire_chart(material) if sc]
    for dc, sc in pts:
        if abs(dc - d) <= 1e-3 * dc:
            return sc, True
    if len(pts) >= 2:
        # log-log interpolation between neighbouring chart sizes (extrapolates at the ends)
        i = max(0, min(len(pts) - 2, sum(1 for dc, _ in pts if dc <= d) - 1))
        (d1, s1), (d2, s2) = pts[i], pts[i + 1]
        slope = math.log(s2 / s1) / math.log(d2 / d1)
        return s1 * (d / d1) ** slope, True
    return mat["A"] / d ** mat["m"], False


END_TYPES = ["Open", "Open & ground", "Closed", "Closed & ground"]

# Number of inactive coils added to active coils for each end type
_END_COILS = {"Open": 0, "Open & ground": 1, "Closed": 2, "Closed & ground": 2}



@dataclass
class SpringInput:
    wire_d: float = 2.0          # mm
    mean_d: float = 18.0         # mm  (OD = mean + d, ID = mean - d)
    active_coils: float = 8.0
    free_length: float = 50.0    # mm
    end_type: str = "Closed & ground"
    material: str = DEFAULT_MATERIAL
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
    sut_from_chart: bool = False
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
    r.sut, r.sut_from_chart = tensile_strength(s.material, d)
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
            "Free length is too short: the coil pitch must be larger than the wire "
            "diameter. Increase free length or reduce coils."
        )
    if C < 4:
        r.warnings.append(f"Spring index C = {C:.2f} is below 4 – hard to coil, high stress.")
    elif C > 16:
        r.warnings.append(f"Spring index C = {C:.2f} is above 16 – prone to tangling and buckling.")
    if r.safety_solid < 1.0:
        r.warnings.append(
            f"Stress at solid is {r.stress_solid / r.allow * 100:.0f}% of the allowable – "
            "spring will take a set if compressed solid."
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
    if wire_chart(s.material) and not in_chart(s.material, d):
        r.warnings.append("Wire diameter is not in this material's wire chart (see the Std… list).")
    return r
