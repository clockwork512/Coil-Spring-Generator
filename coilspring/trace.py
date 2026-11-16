"""Calculation trace for Developer mode.

Re-walks the spring and clamping calculations one variable at a time and records,
for each one: the formula, the formula with the real numbers substituted, what it
depends on, the line of source code that computes it in the app, and whether this
step-by-step value matches the value the app is showing (from calc.compute /
clamp.compute_clamp). Values are in the app's internal units: mm, N, MPa.

If you change a formula in calc.py or clamp.py, the matching entry here will show
"differs" until you update its formula text below too.
"""
from __future__ import annotations

import inspect
import math
import os
import sys
from dataclasses import dataclass, field

from . import calc, clamp

# internal units for each kind of value
UNIT = {"len": "mm", "force": "N", "rate": "N/mm", "stress": "MPa", "mod": "MPa", "deg": "°",
        "hz": "Hz", "mass": "g", "dens": "kg/m³", "area": "mm²", "press": "MPa", "count": "",
        "ratio": "", "pct": "%", "text": "", "psi": "psi"}


@dataclass
class Var:
    key: str
    symbol: str
    name: str
    kind: str
    value: object
    formula: str = ""
    subst: str = ""
    deps: list = field(default_factory=list)
    group: str = ""
    sources: list = field(default_factory=list)      # [(file, line_no, code)]
    check: object = None                             # value the app shows, or None
    check_label: str = ""
    note: str = ""
    used_by: list = field(default_factory=list)

    @property
    def unit(self):
        return UNIT.get(self.kind, "")

    @property
    def matches(self):
        if self.check is None or not isinstance(self.value, (int, float)):
            return None
        a, b = float(self.value), float(self.check)
        if math.isinf(a) and math.isinf(b):
            return True
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def f(v):
    """Compact number for substituted formulas."""
    if isinstance(v, str):
        return v
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "∞"
    return f"{v:.6g}"


# ---------------------------------------------------------------------------
# Source lookup: find the real line that computes each value
# ---------------------------------------------------------------------------
_MODULE_FILES = {}
_LINES = {}


def _source_lines(fname):
    if fname in _LINES:
        return _LINES[fname]
    lines = []
    candidates = []
    mod = sys.modules.get(f"coilspring.{fname[:-3]}")
    if mod is not None:
        try:
            candidates.append(inspect.getsourcefile(mod))
        except (TypeError, OSError):
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, fname))
    candidates.append(os.path.join(here, "web", fname))               # server.py
    candidates.append(os.path.join(here, "web", "static", fname))     # app.js
    base = getattr(sys, "_MEIPASS", None)                 # inside the built .exe
    if base:
        candidates.append(os.path.join(base, "coilspring", fname))
    for c in candidates:
        if c and os.path.exists(c):
            with open(c, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            break
    _LINES[fname] = lines
    return lines


def src(fname, pattern, anchor=None):
    """(file, 1-based line, code) of the first line containing `pattern`,
    searching after the line containing `anchor` if given."""
    lines = _source_lines(fname)
    start = 0
    if anchor:
        for i, ln in enumerate(lines):
            if anchor in ln:
                start = i + 1
                break
    for i in range(start, len(lines)):
        if pattern in lines[i]:
            return (fname, i + 1, lines[i].strip())
    return (fname, 0, pattern + "   (line not found – source may have changed)")


# ---------------------------------------------------------------------------
# Steps that happen in the user interface rather than in calc.py / clamp.py live in
# different files for the desktop app and the website.  Keyed by variable.
WEB_SOURCES = {
    "D": [("app.js", "const mean = S.diaMode")],
    "pct_s": [("app.js", "const ratio = r.allow ? r.stress_solid / r.allow")],
    "Lw": [("app.js", "function workLength")],
    "pct_w": [("app.js", "r.work_stress / r.allow * 100")],
    "c_k": [("server.py", "rate, free, solid = sres.rate")],
    "c_xt": [("app.js", "tol = k.tol_terms.reduce")],
    "c_Ppsi": [("app.js", "const psi = (m) => m / MPA_PER_PSI")],
    "c_tau": [("server.py", "k = sres.bergstrasser * 8 * s.mean_d"), ("server.py", "high=k * r.force_high / c.n_springs")],
    "c_taupct": [("app.js", "const ratio = ws.high / ws.allow")],
}


class Trace:
    def __init__(self, ui: str = "desktop"):
        self.vars: dict[str, Var] = {}
        self.ui = ui                      # "desktop" or "web"

    def add(self, key, symbol, name, kind, value, formula="", subst="", deps=(), group="",
            sources=(), check=None, check_label="", note=""):
        if self.ui == "web" and key in WEB_SOURCES:
            sources = WEB_SOURCES[key]
        self.vars[key] = Var(key, symbol, name, kind, value, formula, subst, list(deps), group,
                             [src(*s) for s in sources], check, check_label, note)
        return value

    def finish(self):
        for v in self.vars.values():
            v.used_by = [k for k, o in self.vars.items() if v.key in o.deps]
        return self

    def __iter__(self):
        return iter(self.vars.values())

    def get(self, key):
        return self.vars.get(key)


END_ANCHOR = {"Open": 'if end_type == "Open":', "Open & ground": 'end_type == "Open & ground"',
              "Closed": 'end_type == "Closed":', "Closed & ground": 'end_type == "Closed & ground"'}


def trace_spring(s: calc.SpringInput, r: calc.SpringResult, dia_mode: int = 0, ui: str = "desktop") -> Trace:
    t = Trace(ui)
    if not r.rate:
        return t.finish()
    d, D, na, l0, et = s.wire_d, s.mean_d, s.active_coils, s.free_length, s.end_type
    mat = calc.MATERIALS[s.material]
    G, rho, allow = mat["G"], mat["rho"], mat["allow"]
    I, C_, M, R, S, MAT, OP = ("Inputs", "Geometry", "Material", "Rate & load", "Stress",
                               "Material", "Operating point")
    CF = "calc.py"
    anchor_c = "def compute("

    # ---- inputs ----
    t.add("d", "d", "Wire diameter", "len", d, "input", group=I,
          sources=[(CF, "d, D, na, l0 = s.wire_d", anchor_c)])
    mode_txt = ["D = OD − d", "D = ID + d", "D = mean diameter (typed in)"][dia_mode]
    t.add("D", "D", "Mean diameter", "len", D, mode_txt,
          note="Set from the OD / ID / Mean box, depending on 'Set by'.", group=I,
          deps=["d"], sources=[("app.py", "mean = v - d if mode == 0")])
    t.add("Na", "Na", "Active coils", "count", na, "input", group=I,
          sources=[(CF, "d, D, na, l0 = s.wire_d", anchor_c)])
    t.add("L0", "L₀", "Free length", "len", l0, "input", group=I,
          sources=[(CF, "d, D, na, l0 = s.wire_d", anchor_c)])
    t.add("ends", "ends", "End type", "text", et, "input", group=I,
          note="Selects which pitch, total-coil and solid-height formulas are used.")
    t.add("OD", "OD", "Outside diameter", "len", s.od, "OD = D + d", f"{f(D)} + {f(d)}", ["D", "d"], C_,
          [(CF, "return self.mean_d + self.wire_d")], s.od, "SpringInput.od")
    t.add("ID", "ID", "Inside diameter", "len", s.id, "ID = D − d", f"{f(D)} − {f(d)}", ["D", "d"], C_,
          [(CF, "return self.mean_d - self.wire_d")], s.id, "SpringInput.id")

    # ---- material ----
    mat_line = (CF, f'"{s.material}"')
    t.add("G", "G", "Shear modulus", "mod", G, "material table", group=MAT, sources=[mat_line],
          note=f"From the {s.material} entry in MATERIALS.")
    t.add("rho", "ρ", "Density", "dens", rho, "material table", group=MAT, sources=[mat_line])
    t.add("allow", "allow", "Allowable fraction of Sut", "ratio", allow, "material table", group=MAT,
          sources=[mat_line])

    # ---- geometry ----
    C = t.add("C", "C", "Spring index", "ratio", D / d, "C = D / d", f"{f(D)} / {f(d)}", ["D", "d"], C_,
              [(CF, "C = D / d", anchor_c)], r.index, "SpringResult.index")
    p_formula = {"Open": ("p = (L₀ − d) / Na", f"({f(l0)} − {f(d)}) / {f(na)}", "return (l0 - d) / na"),
                 "Open & ground": ("p = L₀ / (Na + 1)", f"{f(l0)} / ({f(na)} + 1)", "return l0 / (na + 1)"),
                 "Closed": ("p = (L₀ − 3d) / Na", f"({f(l0)} − 3·{f(d)}) / {f(na)}", "return (l0 - 3 * d) / na"),
                 "Closed & ground": ("p = (L₀ − 2d) / Na", f"({f(l0)} − 2·{f(d)}) / {f(na)}",
                                     "return (l0 - 2 * d) / na")}[et]
    p = t.add("p", "p", "Active pitch", "len", calc.pitch_from_free_length(et, d, na, l0), p_formula[0],
              p_formula[1], ["L0", "d", "Na", "ends"], C_,
              [(CF, "p = pitch_from_free_length(", anchor_c),
               (CF, p_formula[2], "def pitch_from_free_length")], r.pitch, "SpringResult.pitch")
    nt_formula = {"Open": ("Nt = Na", "nt = na"), "Open & ground": ("Nt = Na + 1", "nt = na + 1"),
                  "Closed": ("Nt = Na + 2", "nt = na + 2"), "Closed & ground": ("Nt = Na + 2", "nt = na + 2")}[et]
    nt, _, ls = calc.end_geometry(et, d, na, p)
    t.add("Nt", "Nt", "Total coils", "count", nt, nt_formula[0], f"{f(na)} + {f(nt - na)}" if nt != na else f(na),
          ["Na", "ends"], C_, [(CF, nt_formula[1], END_ANCHOR[et])], r.total_coils, "SpringResult.total_coils")
    ls_formula = {"Open": ("Ls = d·(Nt + 1)", "ls = d * (nt + 1)", f"{f(d)}·({f(nt)} + 1)"),
                  "Open & ground": ("Ls = d·Nt", "ls = d * nt", f"{f(d)}·{f(nt)}"),
                  "Closed": ("Ls = d·(Nt + 1)", "ls = d * (nt + 1)", f"{f(d)}·({f(nt)} + 1)"),
                  "Closed & ground": ("Ls = d·Nt", "ls = d * nt", f"{f(d)}·{f(nt)}")}[et]
    t.add("Ls", "Ls", "Solid height", "len", ls, ls_formula[0], ls_formula[2], ["d", "Nt"], C_,
          [(CF, ls_formula[1], END_ANCHOR[et])], r.solid_length, "SpringResult.solid_length")
    dmax = t.add("dmax", "δmax", "Max deflection (free → solid)", "len", l0 - ls, "δmax = L₀ − Ls",
                 f"{f(l0)} − {f(ls)}", ["L0", "Ls"], C_, [(CF, "r.max_deflection = l0 - ls")],
                 r.max_deflection, "SpringResult.max_deflection")
    lam = t.add("lam", "λ", "Pitch angle", "deg", math.degrees(math.atan(p / (math.pi * D))),
                "λ = atan(p / (π·D))", f"atan({f(p)} / (π·{f(D)}))", ["p", "D"], C_,
                [(CF, "r.pitch_angle_deg =")], r.pitch_angle_deg, "SpringResult.pitch_angle_deg")
    t.add("od_s", "ODs", "OD at solid", "len", math.sqrt(D**2 + (p**2 - d**2) / math.pi**2) + d,
          "ODs = √(D² + (p² − d²)/π²) + d", f"√({f(D)}² + ({f(p)}² − {f(d)}²)/π²) + {f(d)}",
          ["D", "p", "d"], C_, [(CF, "r.od_solid =")], r.od_solid, "SpringResult.od_solid",
          note="Coils open out slightly as the pitch angle goes to zero at solid.")
    Lw = t.add("Lwire", "Lw", "Wire length", "len",
               math.sqrt((math.pi * D) ** 2 + p**2) * na + math.pi * D * (nt - na),
               "Lw = √((π·D)² + p²)·Na + π·D·(Nt − Na)",
               f"√((π·{f(D)})² + {f(p)}²)·{f(na)} + π·{f(D)}·({f(nt)} − {f(na)})",
               ["D", "p", "Na", "Nt"], C_, [(CF, "r.wire_length =")], r.wire_length, "SpringResult.wire_length")
    t.add("mass", "m", "Mass", "mass", rho * (math.pi * (d / 1000) ** 2 / 4) * (Lw / 1000) * 1000,
          "m = ρ·(π·d²/4)·Lw", f"{f(rho)}·(π·({f(d)}/1000)²/4)·({f(Lw)}/1000)·1000",
          ["rho", "d", "Lwire"], C_, [(CF, "r.mass =")], r.mass, "SpringResult.mass",
          note="d and Lw are converted to metres; ×1000 gives grams.")

    # ---- rate & load ----
    k = t.add("k", "k", "Spring rate", "rate", calc.spring_rate(G, d, D, na), "k = G·d⁴ / (8·D³·Na)",
              f"{f(G)}·{f(d)}⁴ / (8·{f(D)}³·{f(na)})", ["G", "d", "D", "Na"], R,
              [(CF, "k = spring_rate(G, d, D, na)", anchor_c), (CF, "return G * d**4 / (8 * D**3 * na)")],
              r.rate, "SpringResult.rate")
    Fs = t.add("Fs", "Fs", "Load at solid", "force", k * dmax, "Fs = k·δmax", f"{f(k)}·{f(dmax)}",
               ["k", "dmax"], R, [(CF, "r.force_solid = k * r.max_deflection")], r.force_solid,
               "SpringResult.force_solid")
    t.add("fn", "fn", "Natural frequency", "hz",
          (d / 1000) / (2 * math.pi * na * (D / 1000) ** 2) * math.sqrt(G * 1e6 / (2 * rho)),
          "fn = d / (2π·Na·D²) · √(G / (2ρ))",
          f"{f(d / 1000)} / (2π·{f(na)}·{f(D / 1000)}²) · √({f(G * 1e6)} / (2·{f(rho)}))",
          ["d", "Na", "D", "G", "rho"], R, [(CF, "r.nat_freq =")], r.nat_freq, "SpringResult.nat_freq",
          note="Both ends against flat plates. d and D in metres, G in Pa.")
    t.add("slender", "L₀/D", "Slenderness", "ratio", l0 / D, "L₀ / D", f"{f(l0)} / {f(D)}", ["L0", "D"], R,
          [(CF, "r.slenderness = l0 / D")], r.slenderness, "SpringResult.slenderness")
    alpha = {"Open": 1.0, "Closed": 0.707}.get(et, 0.5)
    t.add("buck", "(L₀/D)max", "Buckling limit", "ratio", 2.63 / alpha, "(L₀/D)max = 2.63 / α",
          f"2.63 / {f(alpha)}", ["ends"], R,
          [(CF, "alpha = {\"Open\": 1.0"), (CF, "r.buckling_limit = 2.63 / alpha")], r.buckling_limit,
          "SpringResult.buckling_limit", note=f"α = {alpha} for {et} ends (end-condition constant).")

    # ---- stress ----
    Kb = t.add("Kb", "Kb", "Bergsträsser factor", "ratio", (4 * C + 2) / (4 * C - 3), "Kb = (4C + 2) / (4C − 3)",
               f"(4·{f(C)} + 2) / (4·{f(C)} − 3)", ["C"], S, [(CF, "r.bergstrasser =")], r.bergstrasser,
               "SpringResult.bergstrasser", note="Curvature + direct-shear correction used for all stresses.")
    t.add("Kw", "Kw", "Wahl factor (for reference)", "ratio",
          (4 * C - 1) / (4 * C - 4) + 0.615 / C, "Kw = (4C − 1)/(4C − 4) + 0.615/C",
          f"(4·{f(C)} − 1)/(4·{f(C)} − 4) + 0.615/{f(C)}", ["C"], S, [(CF, "r.wahl =")], r.wahl,
          "SpringResult.wahl", note="Calculated but not used; Kb is used instead.")
    tau = t.add("tau_s", "τs", "Stress at solid", "stress", Kb * 8 * Fs * D / (math.pi * d**3),
                "τs = Kb·8·Fs·D / (π·d³)", f"{f(Kb)}·8·{f(Fs)}·{f(D)} / (π·{f(d)}³)",
                ["Kb", "Fs", "D", "d"], S, [(CF, "r.stress_solid =")], r.stress_solid, "SpringResult.stress_solid")
    sut, from_chart = calc.tensile_strength(s.material, d)
    if from_chart:
        t.add("Sut", "Sut", "Tensile strength", "stress", sut, "Sut = from the wire chart (log-log interpolation)",
              "", ["d"], S, [(CF, "r.sut, r.sut_from_chart = tensile_strength("),
                             (CF, "slope = math.log(s2 / s1)")], r.sut, "SpringResult.sut",
              note="This material's wire chart has tensile values, so they are used instead of A / d^m.")
    else:
        t.add("Sut", "Sut", "Tensile strength", "stress", mat["A"] / d ** mat["m"], "Sut = A / d^m",
              f"{f(mat['A'])} / {f(d)}^{f(mat['m'])}", ["d"], S,
              [(CF, "r.sut, r.sut_from_chart = tensile_strength("), (CF, 'return mat["A"] / d ** mat["m"], False')],
              r.sut, "SpringResult.sut", note=f"A = {mat['A']}, m = {mat['m']} from the material table (d in mm).")
    Sa = t.add("Sallow", "Sallow", "Allowable stress at solid", "stress", allow * sut, "Sallow = allow·Sut",
               f"{f(allow)}·{f(sut)}", ["allow", "Sut"], S, [(CF, 'r.allow = mat["allow"] * r.sut')], r.allow,
               "SpringResult.allow")
    t.add("n_s", "n", "Safety factor at solid", "ratio", Sa / tau if tau > 0 else float("inf"),
          "n = Sallow / τs", f"{f(Sa)} / {f(tau)}", ["Sallow", "tau_s"], S, [(CF, "r.safety_solid =")],
          r.safety_solid, "SpringResult.safety_solid")
    t.add("pct_s", "τs/Sallow", "Stress at solid, % of allowable", "pct", tau / Sa * 100, "τs / Sallow × 100",
          f"{f(tau)} / {f(Sa)} × 100", ["tau_s", "Sallow"], S, [("app.py", "ratio = r.stress_solid / r.allow")])

    # ---- operating point ----
    if s.work_length is not None:
        Lw_ = s.work_length
        t.add("Lw", "Lw", "Working length", "len", Lw_, "input (or L₀ − travel)",
              group=OP, deps=["L0"], sources=[("app.py", "def _work_length_from_widget")],
              note="Typed as a travel or a length in the Operating point box.")
        dw = t.add("dw", "δw", "Travel at operating point", "len", l0 - Lw_, "δw = L₀ − Lw", f"{f(l0)} − {f(Lw_)}",
                   ["L0", "Lw"], OP, [(CF, "dx = l0 - s.work_length")], r.work_deflection, "SpringResult.work_deflection")
        Fw = t.add("Fw", "Fw", "Force at operating point", "force", k * dw, "Fw = k·δw", f"{f(k)}·{f(dw)}",
                   ["k", "dw"], OP, [(CF, "r.work_force = k * dx")], r.work_force, "SpringResult.work_force")
        tw = t.add("tau_w", "τw", "Stress at operating point", "stress", Kb * 8 * Fw * D / (math.pi * d**3),
                   "τw = Kb·8·Fw·D / (π·d³)", f"{f(Kb)}·8·{f(Fw)}·{f(D)} / (π·{f(d)}³)", ["Kb", "Fw", "D", "d"], OP,
                   [(CF, "r.work_stress =")], r.work_stress, "SpringResult.work_stress")
        t.add("pct_w", "τw/Sallow", "Operating stress, % of allowable", "pct", tw / Sa * 100,
              "τw / Sallow × 100", f"{f(tw)} / {f(Sa)} × 100", ["tau_w", "Sallow"], OP,
              [("app.py", 'W["% of allowable"].setText')])
    return t.finish()


def trace_clamp(t: Trace, c: clamp.ClampInput, r: clamp.ClampResult, design: bool,
                s: calc.SpringInput | None = None, sres: calc.SpringResult | None = None) -> Trace:
    """Add the clamping-pressure variables to an existing trace."""
    if r is None or not r.force_total:
        return t.finish()
    K, CF = "Clamping pressure", "clamp.py"
    k_dep = ["k"] if design and "k" in t.vars else []
    t.add("c_k", "k₁", "Rate of one spring", "rate", c.rate,
          "= k from Spring design" if design else "input (catalog)", deps=k_dep, group=K,
          sources=[("clamp_page.py", "return r.rate, s.free_length, r.solid_length, r")] if design else [])
    t.add("c_N", "N", "Number of springs", "count", c.n_springs, "input", group=K)
    t.add("c_L0", "L₀", "Free height", "len", c.free_length, "= L₀ from Spring design" if design else "input",
          deps=["L0"] if design else [], group=K)
    t.add("c_Ls", "Ls", "Solid height", "len", c.solid_length, "= Ls from Spring design" if design else "input",
          deps=["Ls"] if design else [], group=K)
    t.add("c_x", "δ", "Displacement", "len", c.displacement, "input", group=K)
    t.add("c_xt", "Δδ", "Deflection tolerance ±", "len", c.disp_tol, "Δδ = sum of the stack-up terms", group=K,
          sources=[("clamp_page.py", "tol = sum(self.tol_terms)")])
    t.add("c_rt", "Δk", "Rate tolerance ±", "ratio", c.rate_tol, "input (fraction)", group=K)
    t.add("c_A", "A", "Contact area", "area", c.area, "input (or length × width)", group=K)
    travel = t.add("c_travel", "s", "Available travel", "len", c.free_length - c.solid_length, "s = L₀ − Ls",
                   f"{f(c.free_length)} − {f(c.solid_length)}", ["c_L0", "c_Ls"], K,
                   [(CF, "r.travel = c.free_length - c.solid_length")], r.travel, "ClampResult.travel")
    t.add("c_h", "h", "Height at load", "len", c.free_length - c.displacement, "h = L₀ − δ",
          f"{f(c.free_length)} − {f(c.displacement)}", ["c_L0", "c_x"], K,
          [(CF, "r.height = c.free_length - c.displacement")], r.height, "ClampResult.height")
    t.add("c_pct", "δ/s", "% of travel used", "pct", c.displacement / travel * 100, "δ / s × 100",
          f"{f(c.displacement)} / {f(travel)} × 100", ["c_x", "c_travel"], K,
          [(CF, "r.pct_travel = c.displacement / r.travel")], r.pct_travel * 100, "ClampResult.pct_travel × 100")
    F1 = t.add("c_F1", "F₁", "Force per spring", "force", c.rate * c.displacement, "F₁ = k₁·δ",
               f"{f(c.rate)}·{f(c.displacement)}", ["c_k", "c_x"], K,
               [(CF, "r.force_spring = c.rate * c.displacement")], r.force_spring, "ClampResult.force_spring")
    Ft = t.add("c_F", "F", "Total force", "force", F1 * c.n_springs, "F = F₁·N", f"{f(F1)}·{f(c.n_springs)}",
               ["c_F1", "c_N"], K, [(CF, "r.force_total = r.force_spring * c.n_springs")], r.force_total,
               "ClampResult.force_total")
    P = t.add("c_P", "P", "Clamping pressure", "press", Ft / c.area, "P = F / A", f"{f(Ft)} / {f(c.area)}",
              ["c_F", "c_A"], K, [(CF, "r.pressure = r.force_total / c.area")], r.pressure, "ClampResult.pressure")
    t.add("c_Ppsi", "P", "Clamping pressure in psi", "psi", P / clamp.MPA_PER_PSI, "P[psi] = P[MPa] / 0.006894757",
          f"{f(P)} / 0.006894757", ["c_P"], K, [("clamp_page.py", "psi = lambda mpa: mpa / MPA_PER_PSI")])
    if c.method == 0:
        tol = t.add("c_tol", "±%", "Force tolerance band (spreadsheet)", "ratio",
                    c.disp_tol / c.displacement + c.rate_tol, "±% = Δδ / δ + Δk",
                    f"{f(c.disp_tol)} / {f(c.displacement)} + {f(c.rate_tol)}", ["c_xt", "c_x", "c_rt"], K,
                    [(CF, "r.tol_frac = c.disp_tol / c.displacement + c.rate_tol")], r.tol_frac, "ClampResult.tol_frac")
        Fl = t.add("c_Flo", "F_low", "Total force, low", "force", Ft * max(1 - tol, 0.0), "F_low = F·(1 − ±%)",
                   f"{f(Ft)}·(1 − {f(tol)})", ["c_F", "c_tol"], K,
                   [(CF, "r.force_low = r.force_total * max(1 - r.tol_frac, 0.0)")], r.force_low, "ClampResult.force_low")
        Fh = t.add("c_Fhi", "F_high", "Total force, high", "force", Ft * (1 + tol), "F_high = F·(1 + ±%)",
                   f"{f(Ft)}·(1 + {f(tol)})", ["c_F", "c_tol"], K,
                   [(CF, "r.force_high = r.force_total * (1 + r.tol_frac)")], r.force_high, "ClampResult.force_high")
    else:
        dlo = max(c.displacement - c.disp_tol, 0.0)
        dhi = min(c.displacement + c.disp_tol, travel)
        Fl = t.add("c_Flo", "F_low", "Total force, low (worst case)", "force",
                   c.n_springs * c.rate * (1 - c.rate_tol) * dlo, "F_low = N·k₁·(1 − Δk)·max(δ − Δδ, 0)",
                   f"{f(c.n_springs)}·{f(c.rate)}·(1 − {f(c.rate_tol)})·{f(dlo)}", ["c_N", "c_k", "c_rt", "c_x", "c_xt"], K,
                   [(CF, "r.force_low = c.n_springs * c.rate * (1 - c.rate_tol) * r.disp_low")], r.force_low,
                   "ClampResult.force_low")
        Fh = t.add("c_Fhi", "F_high", "Total force, high (worst case)", "force",
                   c.n_springs * c.rate * (1 + c.rate_tol) * dhi, "F_high = N·k₁·(1 + Δk)·min(δ + Δδ, s)",
                   f"{f(c.n_springs)}·{f(c.rate)}·(1 + {f(c.rate_tol)})·{f(dhi)}",
                   ["c_N", "c_k", "c_rt", "c_x", "c_xt", "c_travel"], K,
                   [(CF, "r.force_high = c.n_springs * c.rate * (1 + c.rate_tol) * d_hi")], r.force_high,
                   "ClampResult.force_high", note="Capped at solid: a spring can't push harder than at solid height.")
    t.add("c_Plo", "P_low", "Pressure, low", "press", Fl / c.area, "P_low = F_low / A", f"{f(Fl)} / {f(c.area)}",
          ["c_Flo", "c_A"], K, [(CF, "r.pressure_low = r.force_low / c.area")], r.pressure_low, "ClampResult.pressure_low")
    t.add("c_Phi", "P_high", "Pressure, high", "press", Fh / c.area, "P_high = F_high / A", f"{f(Fh)} / {f(c.area)}",
          ["c_Fhi", "c_A"], K, [(CF, "r.pressure_high = r.force_high / c.area")], r.pressure_high,
          "ClampResult.pressure_high")
    if design and s is not None and sres is not None and sres.allow:
        F1h = Fh / c.n_springs
        tau = sres.bergstrasser * 8 * F1h * s.mean_d / (math.pi * s.wire_d ** 3)
        t.add("c_tau", "τ_high", "Wire stress at high load", "stress", tau, "τ_high = Kb·8·(F_high / N)·D / (π·d³)",
              f"{f(sres.bergstrasser)}·8·({f(Fh)} / {f(c.n_springs)})·{f(s.mean_d)} / (π·{f(s.wire_d)}³)",
              ["Kb", "c_Fhi", "c_N", "D", "d"], K,
              [("clamp_page.py", "per_spring_high = r.force_high / self.n"),
               ("clamp_page.py", "tau = sres.bergstrasser * 8 * per_spring_high")])
        t.add("c_taupct", "τ_high/Sallow", "Wire stress at high load, % of allowable", "pct", tau / sres.allow * 100,
              "τ_high / Sallow × 100", f"{f(tau)} / {f(sres.allow)} × 100", ["c_tau", "Sallow"], K,
              [("clamp_page.py", "ratio = tau / sres.allow")])
    return t.finish()
