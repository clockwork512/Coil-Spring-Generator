"""Clamping pressure from identical springs acting in parallel.

Internal units: mm, N, MPa (N/mm^2).  Mirrors the "Parallel Springs" spreadsheet:
every spring gets the same displacement, total force = N x rate x displacement,
pressure = total force / contact area, with a +/- band from tolerances.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KGF = 9.80665
MPA_PER_PSI = 0.006894757

METHODS = ["Spreadsheet (add % tolerances)", "True worst case (stack the extremes)"]


@dataclass
class ClampInput:
    rate: float = 52.0          # N/mm per spring
    n_springs: int = 8
    free_length: float = 17.0   # mm
    solid_length: float = 9.17  # mm
    displacement: float = 4.5   # mm, nominal compression of each spring
    disp_tol: float = 0.35      # +/- mm on the displacement (stack-up)
    rate_tol: float = 0.10      # +/- fraction on spring rate
    area: float = 6000.0        # mm^2 contact area
    method: int = 0             # index into METHODS


@dataclass
class ClampResult:
    travel: float = 0.0          # free - solid
    height: float = 0.0          # free - displacement
    pct_travel: float = 0.0      # displacement / travel
    force_spring: float = 0.0    # N, nominal, one spring
    force_total: float = 0.0     # N, nominal, all springs
    pressure: float = 0.0        # MPa, nominal
    tol_frac: float = 0.0        # +/- band as a fraction (spreadsheet method)
    force_low: float = 0.0
    force_high: float = 0.0
    pressure_low: float = 0.0
    pressure_high: float = 0.0
    disp_low: float = 0.0
    disp_high: float = 0.0
    status: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def compute_clamp(c: ClampInput) -> ClampResult:
    r = ClampResult()
    if c.rate <= 0:
        r.errors.append("Spring rate must be positive.")
    if c.n_springs < 1:
        r.errors.append("Need at least one spring.")
    if c.area <= 0:
        r.errors.append("Contact area must be positive.")
    if c.free_length <= c.solid_length:
        r.errors.append("Free height must be larger than solid height.")
    if c.displacement <= 0:
        r.errors.append("Displacement must be positive.")
    if r.errors:
        return r

    r.travel = c.free_length - c.solid_length
    r.height = c.free_length - c.displacement
    r.pct_travel = c.displacement / r.travel

    r.force_spring = c.rate * c.displacement
    r.force_total = r.force_spring * c.n_springs
    r.pressure = r.force_total / c.area

    r.disp_low = max(c.displacement - c.disp_tol, 0.0)
    r.disp_high = c.displacement + c.disp_tol

    if c.method == 0:
        # Spreadsheet: band = (deflection tol / displacement) + rate tol, applied to nominal
        r.tol_frac = c.disp_tol / c.displacement + c.rate_tol
        r.force_low = r.force_total * max(1 - r.tol_frac, 0.0)
        r.force_high = r.force_total * (1 + r.tol_frac)
    else:
        # Exact extremes: soft spring at the short stack vs stiff spring at the long stack.
        # A spring can't push harder than it does at solid, so cap the high deflection there.
        d_hi = min(r.disp_high, r.travel)
        r.force_low = c.n_springs * c.rate * (1 - c.rate_tol) * r.disp_low
        r.force_high = c.n_springs * c.rate * (1 + c.rate_tol) * d_hi
        r.tol_frac = (r.force_high - r.force_total) / r.force_total
    r.pressure_low = r.force_low / c.area
    r.pressure_high = r.force_high / c.area

    if c.displacement > r.travel:
        r.status = "Exceeds solid height!"
        r.errors.append("Displacement is more than the spring's travel – it would be solid.")
    elif r.pct_travel > 0.8:
        r.status = "Near solid (>80%)"
        r.warnings.append(f"Springs are {r.pct_travel * 100:.0f}% compressed – keep below 80% "
                          "so the rate stays linear and there's margin for tolerance.")
    else:
        r.status = "OK"
    if r.disp_high > r.travel and c.displacement <= r.travel:
        r.warnings.append("At the high end of the deflection tolerance the springs go solid – "
                          "clamping force is then set by the hardware, not the springs.")
    if c.disp_tol >= c.displacement:
        r.warnings.append("Deflection tolerance is as large as the displacement – "
                          "at the low end the springs may not touch at all.")
    return r


def pressure_curve(c: ClampInput, points: int = 60):
    """(displacement mm, nominal MPa, low MPa, high MPa) arrays from 0 to solid."""
    import numpy as np
    travel = max(c.free_length - c.solid_length, 1e-9)
    x = np.linspace(0, travel, points)
    nominal = c.n_springs * c.rate * x / c.area
    if c.method == 0:
        # band defined relative to the chosen displacement, so it scales with load
        tol = c.disp_tol / max(c.displacement, 1e-9) + c.rate_tol
        low, high = nominal * max(1 - tol, 0), nominal * (1 + tol)
    else:
        low = c.n_springs * c.rate * (1 - c.rate_tol) * np.clip(x - c.disp_tol, 0, None) / c.area
        high = c.n_springs * c.rate * (1 + c.rate_tol) * np.clip(x + c.disp_tol, 0, travel) / c.area
    return x, nominal, low, high
