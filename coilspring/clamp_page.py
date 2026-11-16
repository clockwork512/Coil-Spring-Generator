"""'Clamping pressure' page: N identical springs pressing on a contact area."""
from __future__ import annotations

import math
import re
from dataclasses import asdict

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QFormLayout, QGroupBox, QLabel, QComboBox,
    QSpinBox, QAbstractSpinBox, QLineEdit, QPushButton, QScrollArea, QFrame, QSizePolicy,
)

from .app import MetricCard, spin, MM_PER_IN, keep
from .clamp import ClampInput, compute_clamp, pressure_curve, METHODS, MPA_PER_PSI, KGF
from . import theme
from .theme import c as tc, T, span

MM2_PER_IN2 = MM_PER_IN ** 2


def _parse_sum(text: str):
    """'0.1+0.05+0.05' -> [0.1, 0.05, 0.05]; None if it isn't a list of numbers."""
    parts = [p for p in re.split(r"[+,;]", text.replace(" ", "")) if p]
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return None
    return vals if vals and all(v >= 0 for v in vals) else None


class ClampPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._loading = False
        # state in mm / N (defaults = the "Parallel Springs" sheet, LHP 063D 02S)
        self.source = 1                      # 0 = this spring design, 1 = catalog values
        self.cat_rate = 5.3 * KGF            # N/mm
        self.cat_free = 17.0
        self.cat_solid = 9.17
        self.part_no = "LHP 063D 02S"
        self.n = 8
        self.disp = 4.5
        self.tol_terms = [0.1, 0.05, 0.05, 0.05, 0.05, 0.05]   # mm
        self.rate_tol = 0.10
        self.area_mode = 0                   # 0 = area, 1 = length x width
        self.area = 6000.0                   # mm^2
        self.area_L, self.area_W = 100.0, 60.0
        self.method = 0
        self.c = ClampInput()
        self.r = None
        self._build()
        self.refresh_units()

    # ------------------------------------------------------------------ UI
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QWidget()
        left.setObjectName("panel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 16, 16, 16)
        lv.setSpacing(14)

        g = QGroupBox("Spring")
        f = QFormLayout(g)
        self.f_spring = f
        self.w_source = QComboBox()
        self.w_source.addItems(["This spring design", "Catalog spring (enter values)"])
        f.addRow("Use", self.w_source)
        self.w_part = QLineEdit()
        self.w_part.setPlaceholderText("optional")
        f.addRow("Part number", self.w_part)
        self.w_rate = spin(0.0001, 1e7, 4, 0.05)
        f.addRow("Rate (each)", self.w_rate)
        self.w_free = spin(0.001, 1e5, 3, 0.05)
        f.addRow("Free height", self.w_free)
        self.w_solid = spin(0.0, 1e5, 3, 0.05)
        f.addRow("Solid height", self.w_solid)
        self.w_source_hint = QLabel()
        self.w_source_hint.setObjectName("hint")
        self.w_source_hint.setWordWrap(True)
        f.addRow(self.w_source_hint)
        lv.addWidget(g)

        g = QGroupBox("Assembly")
        f = QFormLayout(g)
        self.w_n = QSpinBox()
        self.w_n.setRange(1, 1000)
        self.w_n.setAlignment(Qt.AlignRight)
        self.w_n.setSuffix("  springs")
        f.addRow("Number", self.w_n)
        self.w_disp = spin(0.0001, 1e5, 3, 0.1)
        self.w_disp.setToolTip("How far each spring is compressed from its free height")
        f.addRow("Displacement", self.w_disp)
        self.w_tol = QLineEdit()
        self.w_tol.setToolTip("± stack-up on the displacement. Type one value, or add up\n"
                              "the contributors, e.g.  0.1 + 0.05 + 0.05")
        f.addRow("Deflection tol ±", self.w_tol)
        self.w_tol_hint = QLabel()
        self.w_tol_hint.setObjectName("hint")
        f.addRow("", self.w_tol_hint)
        self.w_rtol = spin(0.0, 100, 1, 1.0, "  %")
        self.w_rtol.setToolTip("Manufacturer's spring-rate tolerance, ± %")
        f.addRow("Rate tol ±", self.w_rtol)
        lv.addWidget(g)

        g = QGroupBox("Contact area")
        f = QFormLayout(g)
        self.f_area = f
        self.w_area_mode = QComboBox()
        self.w_area_mode.addItems(["Enter area", "Length × width"])
        f.addRow("Set by", self.w_area_mode)
        self.w_area = spin(0.0001, 1e9, 2, 10)
        f.addRow("Area", self.w_area)
        self.w_L = spin(0.001, 1e5, 3, 1)
        f.addRow("Length", self.w_L)
        self.w_W = spin(0.001, 1e5, 3, 1)
        f.addRow("Width", self.w_W)
        self.w_area_hint = QLabel()
        self.w_area_hint.setObjectName("hint")
        f.addRow("", self.w_area_hint)
        lv.addWidget(g)

        g = QGroupBox("Tolerance method")
        f = QFormLayout(g)
        self.w_method = QComboBox()
        self.w_method.addItems(METHODS)
        self.w_method.setToolTip(
            "Spreadsheet: band = deflection tol ÷ displacement + rate tol, applied to the nominal.\n"
            "True worst case: (rate × (1 ± rate tol)) × (displacement ± deflection tol),\n"
            "capped at solid height.")
        f.addRow(self.w_method)
        lv.addWidget(g)

        copy_btn = QPushButton("Copy results")
        copy_btn.clicked.connect(self.copy_results)
        lv.addWidget(copy_btn)
        lv.addStretch()

        lscroll = QScrollArea()
        lscroll.setWidgetResizable(True)
        lscroll.setFrameShape(QFrame.NoFrame)
        lscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lscroll.setWidget(left)
        lscroll.setFixedWidth(380)
        root.addWidget(lscroll)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setObjectName("sep")
        root.addWidget(sep)

        right = QWidget()
        right.setObjectName("panel")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 16)
        rv.setSpacing(10)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.card_p = MetricCard("Clamping pressure")
        self.card_range = MetricCard("Pressure range (tolerance)")
        self.card_force = MetricCard("Total force")
        self.card_travel = MetricCard("Spring compression")
        self.card_stress = MetricCard("Wire stress at high load")
        for card, key in ((self.card_p, "c_P"), (self.card_range, "c_Phi"), (self.card_force, "c_F"),
                          (self.card_travel, "c_pct"), (self.card_stress, "c_tau")):
            card.set_dev(key)
        grid.addWidget(self.card_p, 0, 0)
        grid.addWidget(self.card_range, 0, 1)
        grid.addWidget(self.card_force, 1, 0)
        grid.addWidget(self.card_travel, 1, 1)
        grid.addWidget(self.card_stress, 2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        rv.addLayout(grid)

        self.w_warn = QLabel()
        self.w_warn.setObjectName("warn")
        self.w_warn.setWordWrap(True)
        self.w_warn.setTextFormat(Qt.RichText)
        rv.addWidget(self.w_warn)

        import pyqtgraph as pg
        self.pg = pg
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(260)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.c_low = self.plot.plot()
        self.c_high = self.plot.plot()
        self.fill = pg.FillBetweenItem(self.c_low, self.c_high)
        self.plot.addItem(self.fill)
        self.c_nom = self.plot.plot()
        self.solid_line = pg.InfiniteLine(angle=90, label="solid", labelOpts=dict(position=0.92))
        self.plot.addItem(self.solid_line)
        self.err = pg.ErrorBarItem(x=np.array([0.0]), y=np.array([0.0]), top=np.array([0.0]),
                                   bottom=np.array([0.0]), beam=0.0)
        self.plot.addItem(self.err)
        self.marker = pg.ScatterPlotItem(size=11, pen=None)
        self.plot.addItem(self.marker)
        self.apply_theme()
        rv.addWidget(self.plot, 1)

        rscroll = QScrollArea()
        rscroll.setWidgetResizable(True)
        rscroll.setFrameShape(QFrame.NoFrame)
        rscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rscroll.setWidget(right)
        root.addWidget(rscroll, 1)

        for w in (self.w_rate, self.w_free, self.w_solid, self.w_disp, self.w_rtol,
                  self.w_area, self.w_L, self.w_W):
            w.valueChanged.connect(self.on_input)
        self.w_n.valueChanged.connect(self.on_input)
        self.w_tol.textChanged.connect(self.on_input)
        self.w_part.textChanged.connect(self.on_input)
        for w in (self.w_source, self.w_area_mode, self.w_method):
            w.currentIndexChanged.connect(self.on_mode)

    def apply_theme(self):
        pg = self.pg
        theme.style_plot(self.plot)
        dashed = pg.mkPen(tc("accent"), width=1, style=Qt.DashLine)
        self.c_low.setPen(dashed)
        self.c_high.setPen(dashed)
        self.fill.setBrush(pg.mkBrush(*T["band"]))
        self.c_nom.setPen(pg.mkPen(tc("wire"), width=2.5))
        self.solid_line.setPen(pg.mkPen(tc("dim"), width=1, style=Qt.DashLine))
        self.solid_line.label.setColor(tc("dim"))
        self.err.setData(pen=pg.mkPen(tc("accent"), width=2))
        self.marker.setBrush(pg.mkBrush(tc("accent")))
        if self.r is not None:
            self.update_results()

    # ------------------------------------------------------- state <-> UI
    def _area_disp(self, mm2):
        return mm2 / MM2_PER_IN2 if self.main.u.imperial else mm2

    def _area_in(self, v):
        return v * MM2_PER_IN2 if self.main.u.imperial else v

    @property
    def area_unit(self):
        return "in²" if self.main.u.imperial else "mm²"

    def _fmt_len_term(self, mm):
        v = self.main.u.len(mm)
        return f"{v:.{5 if self.main.u.imperial else 4}f}".rstrip("0").rstrip(".") if v else "0"

    def refresh_units(self):
        """Push the stored (mm / N) state into the widgets in the current units."""
        u = self.main.u
        self._loading = True
        dec = 4 if u.imperial else 3
        for w in (self.w_free, self.w_solid, self.w_disp, self.w_L, self.w_W):
            w.setDecimals(dec)
            w.setSuffix(f"  {u.len_unit}")
            w.setSingleStep(0.005 if u.imperial else 0.1)
        self.w_rate.setSuffix(f"  {u.rate_unit}")
        self.w_area.setSuffix(f"  {self.area_unit}")
        self.w_area.setDecimals(4 if u.imperial else 1)
        self.w_area.setSingleStep(0.1 if u.imperial else 10)

        self.w_source.setCurrentIndex(self.source)
        self.w_part.setText(self.part_no)
        self.w_rate.setValue(u.rate(self.cat_rate))
        self.w_free.setValue(u.len(self.cat_free))
        self.w_solid.setValue(u.len(self.cat_solid))
        self.w_n.setValue(self.n)
        self.w_disp.setValue(u.len(self.disp))
        self.w_tol.setText(" + ".join(self._fmt_len_term(t) for t in self.tol_terms))
        self.w_rtol.setValue(self.rate_tol * 100)
        self.w_area_mode.setCurrentIndex(self.area_mode)
        self.w_area.setValue(self._area_disp(self.area))
        self.w_L.setValue(u.len(self.area_L))
        self.w_W.setValue(u.len(self.area_W))
        self.w_method.setCurrentIndex(self.method)
        self._loading = False
        self._apply_modes()
        self.update_results()

    def _read(self):
        u = self.main.u
        self.source = self.w_source.currentIndex()
        self.part_no = self.w_part.text()
        # keep(): only re-read a box the person actually changed (see app.keep)
        if self.source == 1:
            self.cat_rate = keep(self.cat_rate, self.w_rate, u.rate, u.rate_in)
            self.cat_free = keep(self.cat_free, self.w_free, u.len, u.len_in)
            self.cat_solid = keep(self.cat_solid, self.w_solid, u.len, u.len_in)
        self.n = self.w_n.value()
        self.disp = keep(self.disp, self.w_disp, u.len, u.len_in)
        shown_tol = " + ".join(self._fmt_len_term(t) for t in self.tol_terms)
        terms = _parse_sum(self.w_tol.text())
        self._tol_ok = terms is not None
        if terms is not None and self.w_tol.text().replace(" ", "") != shown_tol.replace(" ", ""):
            self.tol_terms = [u.len_in(t) for t in terms]
        self.rate_tol = keep(self.rate_tol, self.w_rtol, lambda x: x * 100, lambda x: x / 100)
        self.area_mode = self.w_area_mode.currentIndex()
        self.area_L = keep(self.area_L, self.w_L, u.len, u.len_in)
        self.area_W = keep(self.area_W, self.w_W, u.len, u.len_in)
        self.area = (self.area_L * self.area_W if self.area_mode == 1
                     else keep(self.area, self.w_area, self._area_disp, self._area_in))
        self.method = self.w_method.currentIndex()

    def _apply_modes(self):
        design = self.w_source.currentIndex() == 0
        for w in (self.w_rate, self.w_free, self.w_solid):
            w.setReadOnly(design)
            w.style().unpolish(w)
            w.style().polish(w)
        self.w_source_hint.setText("Rate, free and solid height come from the Spring design page."
                                   if design else "Values from the spring catalog / datasheet.")
        by_lw = self.w_area_mode.currentIndex() == 1
        self.f_area.setRowVisible(self.w_area, not by_lw)
        self.f_area.setRowVisible(self.w_L, by_lw)
        self.f_area.setRowVisible(self.w_W, by_lw)
        self.card_stress.setVisible(design)
        self.f_spring.setRowVisible(self.w_part, not design)

    def on_mode(self, *_):
        if self._loading:
            return
        if self.w_source.currentIndex() == 1 and self.source == 0:
            # back to catalog values: show the saved catalog spring, not the design's numbers
            u = self.main.u
            self._loading = True
            self.w_rate.setValue(u.rate(self.cat_rate))
            self.w_free.setValue(u.len(self.cat_free))
            self.w_solid.setValue(u.len(self.cat_solid))
            self._loading = False
        self._apply_modes()
        self.on_input()

    def on_input(self, *_):
        if self._loading:
            return
        self._read()
        self.update_results()

    # ------------------------------------------------------------ results
    def _spring_values(self):
        """(rate N/mm, free mm, solid mm, spring result or None) for the chosen source."""
        if self.source == 0:
            r = self.main.r
            s = self.main.s
            if r is None or not r.rate:
                return None
            return r.rate, s.free_length, r.solid_length, r
        return self.cat_rate, self.cat_free, self.cat_solid, None

    def update_results(self):
        """Recalculate, then refresh the developer inspector if it's open."""
        try:
            self._update_results()
        finally:
            refresh = getattr(self.main, "refresh_dev", None)
            if refresh and not self._loading:
                refresh()

    def _update_results(self):
        """Recalculate; also called by the main window whenever the spring design changes."""
        if self._loading:
            return
        u = self.main.u
        if self.source == 0:
            sv = self._spring_values()
            if sv:
                self._loading = True
                self.w_rate.setValue(u.rate(sv[0]))
                self.w_free.setValue(u.len(sv[1]))
                self.w_solid.setValue(u.len(sv[2]))
                self._loading = False
        sv = self._spring_values()
        tol = sum(self.tol_terms)
        self.w_tol_hint.setText(f"= ± {u.fl(tol)}" + ("" if getattr(self, "_tol_ok", True)
                                                     else "   (can't read that – using last value)"))
        self.w_area_hint.setText(
            f"= {self._area_disp(self.area):,.{4 if u.imperial else 0}f} {self.area_unit}"
            if self.area_mode == 1 else
            f"≈ {math.sqrt(self.area) / (MM_PER_IN if u.imperial else 1):.3f} {u.len_unit} square")
        if sv is None:
            self._blank("Spring design isn't valid – fix it on the Spring design page.")
            return
        rate, free, solid, sres = sv
        self.c = ClampInput(rate=rate, n_springs=self.n, free_length=free, solid_length=solid,
                            displacement=self.disp, disp_tol=tol, rate_tol=self.rate_tol,
                            area=self.area, method=self.method)
        r = self.r = compute_clamp(self.c)
        if not r.ok and r.force_total == 0:
            self._blank("<br>".join(r.errors))
            return

        psi = lambda mpa: mpa / MPA_PER_PSI
        self.card_p.set(f"{psi(r.pressure):.2f} psi",
                        f"{r.pressure:.4f} MPa  ·  {r.pressure * 1000:.1f} kPa  ·  "
                        f"{r.pressure * 1e6 / KGF / 1e4:.3f} kgf/cm²")
        lo_pct = (1 - r.pressure_low / r.pressure) * 100
        hi_pct = (r.pressure_high / r.pressure - 1) * 100
        band = (f"±{hi_pct:.1f}%" if abs(lo_pct - hi_pct) < 0.05
                else f"−{lo_pct:.1f}% / +{hi_pct:.1f}%")
        self.card_range.set(f"{psi(r.pressure_low):.1f} – {psi(r.pressure_high):.1f} psi",
                            f"{r.pressure_low:.4f} – {r.pressure_high:.4f} MPa  ·  {band}")
        self.card_force.set(u.ff(r.force_total),
                            f"{self.n} × {u.ff(r.force_spring)}  ·  {r.force_total:,.1f} N  ·  "
                            f"{r.force_total / KGF:,.1f} kgf")
        state = "bad" if r.errors else "warn" if r.pct_travel > 0.8 else "good"
        self.card_travel.set(f"{r.pct_travel * 100:.0f}%  ·  {r.status}",
                             f"of {u.fl(r.travel)} travel  ·  height {u.fl(r.height)}", state)

        if sres is not None and sres.allow:
            s = self.main.s
            per_spring_high = r.force_high / self.n
            tau = sres.bergstrasser * 8 * per_spring_high * s.mean_d / (math.pi * s.wire_d ** 3)
            tau_nom = sres.bergstrasser * 8 * r.force_spring * s.mean_d / (math.pi * s.wire_d ** 3)
            ratio = tau / sres.allow
            self.card_stress.set(u.fs(tau),
                                 f"{ratio * 100:.0f}% of allowable {u.fs(sres.allow)}  ·  "
                                 f"nominal {u.fs(tau_nom)}",
                                 "bad" if ratio > 1 else "warn" if ratio > 0.85 else "good")

        msgs = [span("bad", f"<b>✕</b> {e}") for e in r.errors]
        msgs += [span("warn", f"<b>!</b> {w}") for w in r.warnings]
        self.w_warn.setText("<br><br>".join(msgs) if msgs else span("good", "✓ No issues."))
        self._update_chart(u)

    def _blank(self, msg):
        for c in (self.card_p, self.card_range, self.card_force, self.card_travel, self.card_stress):
            c.set("—")
        self.w_warn.setText(span("bad", f"<b>✕</b> {msg}"))
        for c in (self.c_nom, self.c_low, self.c_high):
            c.setData([], [])
        self.marker.setData([], [])

    def _update_chart(self, u):
        c, r = self.c, self.r
        x, nom, lo, hi = pressure_curve(c)
        psi = 1 / MPA_PER_PSI
        xd = u.len_arr(x)
        self.c_nom.setData(xd, nom * psi)
        self.c_low.setData(xd, lo * psi)
        self.c_high.setData(xd, hi * psi)
        xm = u.len(c.displacement)
        self.marker.setData([xm], [r.pressure * psi])
        self.err.setData(x=np.array([xm]), y=np.array([r.pressure * psi]),
                         top=np.array([(r.pressure_high - r.pressure) * psi]),
                         bottom=np.array([(r.pressure - r.pressure_low) * psi]))
        self.solid_line.setValue(u.len(r.travel))
        self.plot.setLabel("bottom", f"Displacement ({u.len_unit})")
        self.plot.setLabel("left", "Pressure (psi)")
        self.plot.setXRange(0, u.len(r.travel) * 1.04, padding=0)
        self.plot.setYRange(0, max(hi.max(), r.pressure_high) * psi * 1.08, padding=0)

    # ---------------------------------------------------------- utilities
    def copy_results(self):
        if not self.r or not self.r.ok and self.r.force_total == 0:
            return
        u, c, r = self.main.u, self.c, self.r
        psi = lambda mpa: mpa / MPA_PER_PSI
        src = "Spring design" if self.source == 0 else "Catalog spring"
        lines = [
            "SPRINGS IN PARALLEL – CLAMPING PRESSURE",
            f"Spring:               {src}"
            + (f"  ({self.part_no})" if self.part_no and self.source == 1 else ""),
            f"Rate (each):          {u.fr(c.rate)}",
            f"Free / solid height:  {u.fl(c.free_length)} / {u.fl(c.solid_length)}",
            f"Number of springs:    {c.n_springs}",
            f"Displacement:         {u.fl(c.displacement)}  (± {u.fl(c.disp_tol)})",
            f"Rate tolerance:       ± {c.rate_tol * 100:.1f}%",
            f"Contact area:         {self._area_disp(c.area):,.4g} {self.area_unit}",
            f"Height at load:       {u.fl(r.height)}",
            f"% of travel:          {r.pct_travel * 100:.1f}%  ({r.status})",
            f"Force per spring:     {u.ff(r.force_spring)}",
            f"Total force:          {u.ff(r.force_total)}  ({r.force_total:,.1f} N)",
            f"Pressure:             {psi(r.pressure):.2f} psi  ({r.pressure:.4f} MPa)",
            f"Pressure low / high:  {psi(r.pressure_low):.2f} / {psi(r.pressure_high):.2f} psi"
            f"  ({METHODS[c.method].split(' (')[0].lower()} method)",
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.main.statusBar().showMessage("Clamping results copied to clipboard", 4000)

    def get_state(self) -> dict:
        self._read()
        keys = ("source", "cat_rate", "cat_free", "cat_solid", "part_no", "n", "disp", "tol_terms",
                "rate_tol", "area_mode", "area", "area_L", "area_W", "method")
        return {k: getattr(self, k) for k in keys}

    def set_state(self, d: dict):
        for k, v in (d or {}).items():
            if hasattr(self, k) and not callable(getattr(self, k)):
                setattr(self, k, v)
        self.refresh_units()
