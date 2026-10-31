"""Coil Spring Designer – main window."""
from __future__ import annotations

import json
import math
import sys
import traceback

import numpy as np
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRunnable, QThreadPool, QSettings
from PySide6.QtGui import QAction, QFont, QKeySequence, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QGroupBox, QLabel, QDoubleSpinBox, QComboBox, QRadioButton, QButtonGroup, QCheckBox,
    QPushButton, QTabWidget, QFileDialog, QMessageBox, QScrollArea, QFrame, QSplitter,
    QSizePolicy, QToolBar, QStatusBar,
)

from .calc import (
    SpringInput, SpringResult, compute, MATERIALS, END_TYPES, MM_PER_IN, N_PER_LBF, MPA_PER_KSI,
    active_coils_for_rate, wire_d_for_rate,
)
from .views import make_3d_view, SpringDrawing, LoadChart

APP_NAME = "Coil Spring Designer"
VERSION = "1.0"

WIRE_SIZES_IN = [0.010, 0.012, 0.014, 0.016, 0.018, 0.020, 0.022, 0.024, 0.026, 0.029, 0.031, 0.033,
                 0.035, 0.037, 0.039, 0.041, 0.043, 0.045, 0.047, 0.049, 0.051, 0.055, 0.059, 0.063,
                 0.067, 0.071, 0.075, 0.080, 0.085, 0.090, 0.095, 0.100, 0.106, 0.112, 0.118, 0.125,
                 0.135, 0.148, 0.162, 0.177, 0.192, 0.207, 0.225, 0.250, 0.281, 0.312, 0.375, 0.437, 0.500]
WIRE_SIZES_MM = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.63, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2,
                 1.25, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.0, 3.2, 3.5, 3.6, 4.0, 4.5, 5.0, 5.5,
                 5.6, 6.0, 6.3, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 12.5]


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
KGF = 9.80665  # newtons per kilogram-force

UNIT_SYSTEMS = ["Inch  (in, lbf)", "Metric  (mm, N)", "Metric  (mm, kgf)"]


class Units:
    """system: 0 = inch/lbf, 1 = mm/N, 2 = mm/kgf"""

    def __init__(self, system: int):
        self.system = system
        self.imperial = system == 0
        self.kg = system == 2
        # newtons per displayed force unit
        self._fN = N_PER_LBF if self.imperial else KGF if self.kg else 1.0
        # MPa per displayed stress unit
        self._sM = MPA_PER_KSI if self.imperial else KGF if self.kg else 1.0

    @property
    def len_unit(self): return "in" if self.imperial else "mm"
    @property
    def force_unit(self): return "lbf" if self.imperial else "kgf" if self.kg else "N"
    @property
    def rate_unit(self): return f"{self.force_unit}/{self.len_unit}"
    @property
    def stress_unit(self): return "ksi" if self.imperial else "kgf/mm²" if self.kg else "MPa"
    @property
    def mass_unit(self): return "oz" if self.imperial else "g"
    @property
    def len_decimals(self): return 4 if self.imperial else 3

    def len(self, mm): return mm / MM_PER_IN if self.imperial else mm
    def len_in(self, v): return v * MM_PER_IN if self.imperial else v
    def len_arr(self, a): return np.asarray(a) / MM_PER_IN if self.imperial else np.asarray(a)
    def force(self, n): return n / self._fN
    def force_arr(self, a): return np.asarray(a) / self._fN
    def force_in(self, v): return v * self._fN
    def rate(self, n_mm): return n_mm * self.len_in(1.0) / self._fN
    def rate_in(self, v): return v * self._fN / self.len_in(1.0)
    def stress(self, mpa): return mpa / self._sM
    def mass(self, g): return g / 28.349523 if self.imperial else g

    def fl(self, mm): return f"{self.len(mm):.{4 if self.imperial else 2}f} {self.len_unit}"
    def ff(self, n): return f"{self.force(n):.2f} {self.force_unit}"
    def fr(self, k): return f"{self.rate(k):.3f} {self.rate_unit}"
    def fs(self, mpa): return f"{self.stress(mpa):.1f} {self.stress_unit}"


# ---------------------------------------------------------------------------
# Background export
# ---------------------------------------------------------------------------
class _Signals(QObject):
    done = Signal(str)
    failed = Signal(str)


class ExportJob(QRunnable):
    def __init__(self, s: SpringInput, path: str, kind: str):
        super().__init__()
        self.s, self.path, self.kind = s, path, kind
        self.signals = _Signals()

    def run(self):
        try:
            from . import geometry
            if self.kind == "step":
                geometry.export_step(self.s, self.path)
            else:
                geometry.export_stl(self.s, self.path)
            self.signals.done.emit(self.path)
        except Exception:
            self.signals.failed.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# Small widgets
# ---------------------------------------------------------------------------
def spin(minimum=0.0, maximum=1e6, decimals=3, step=0.1, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(minimum, maximum)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setSuffix(suffix)
    w.setKeyboardTracking(False)
    w.setAccelerated(True)
    w.setAlignment(Qt.AlignRight)
    return w


class MetricCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel(title.upper())
        self.title.setObjectName("cardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("cardValue")
        self.sub = QLabel("")
        self.sub.setObjectName("cardSub")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value, sub="", state=None):
        self.value.setText(value)
        self.sub.setText(sub)
        self.value.setProperty("state", state or "")
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.settings = QSettings("CoilSpringDesigner", "CoilSpringDesigner")
        try:
            system = int(self.settings.value("units_system", -1))
        except (TypeError, ValueError):
            system = -1
        if system not in (0, 1, 2):   # migrate the old on/off setting
            system = 0 if self.settings.value("imperial", "true") == "true" else 1
        self.u = Units(system)
        self.s = SpringInput(wire_d=0.080 * MM_PER_IN, mean_d=(0.750 - 0.080) * MM_PER_IN,
                             active_coils=8, free_length=2.0 * MM_PER_IN)
        self.r = SpringResult()
        self._loading = False
        self.pool = QThreadPool.globalInstance()
        self.current_path = None

        self._build_ui()
        self._apply_units_to_widgets()
        self._push_state_to_widgets()

        self.timer = QTimer(self, singleShot=True, interval=60)
        self.timer.timeout.connect(self.recompute)
        self.recompute()

    # ---------------- UI construction ----------------
    def _build_ui(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)

        def act(text, slot, shortcut=None, primary=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            tb.addAction(a)
            if primary:
                tb.widgetForAction(a).setObjectName("primary")
            return a

        act("New", self.new_design, "Ctrl+N")
        act("Open…", self.open_design, "Ctrl+O")
        act("Save…", self.save_design, "Ctrl+S")
        tb.addSeparator()
        act("Copy spec", self.copy_spec, "Ctrl+Shift+C")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(QLabel("Units "))
        self.units_combo = QComboBox()
        self.units_combo.addItems(UNIT_SYSTEMS)
        self.units_combo.setCurrentIndex(self.u.system)
        self.units_combo.currentIndexChanged.connect(self.on_units_changed)
        tb.addWidget(self.units_combo)
        tb.addSeparator()
        self.stl_action = act("Export STL", lambda: self.export("stl"))
        self.step_action = act("Export STEP", lambda: self.export("step"), "Ctrl+E", primary=True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        self.setCentralWidget(splitter)

        # ---- left: inputs ----
        left = QWidget()
        left.setObjectName("panel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 16, 16, 16)
        lv.setSpacing(14)

        # Material
        g = QGroupBox("Material")
        f = QFormLayout(g)
        self.material = QComboBox()
        self.material.addItems(MATERIALS.keys())
        f.addRow(self.material)
        self.mat_info = QLabel()
        self.mat_info.setObjectName("hint")
        f.addRow(self.mat_info)
        lv.addWidget(g)

        # Wire & diameter
        g = QGroupBox("Wire and diameter")
        f = QFormLayout(g)
        f.setLabelAlignment(Qt.AlignLeft)
        wrow = QHBoxLayout()
        self.wire_d = spin(0.001, 1000, 4, 0.001)
        self.wire_std = QComboBox()
        self.wire_std.setToolTip("Standard wire sizes")
        self.wire_std.setMaximumWidth(90)
        wrow.addWidget(self.wire_d, 1)
        wrow.addWidget(self.wire_std)
        f.addRow("Wire Ø", wrow)

        dm = QHBoxLayout()
        self.dia_group = QButtonGroup(self)
        for i, t in enumerate(("OD", "ID", "Mean")):
            rb = QRadioButton(t)
            self.dia_group.addButton(rb, i)
            dm.addWidget(rb)
        self.dia_group.button(0).setChecked(True)
        dm.addStretch()
        f.addRow("Set by", dm)
        self.dia_val = spin(0.001, 10000, 4, 0.01)
        self.dia_label = QLabel("OD")
        f.addRow(self.dia_label, self.dia_val)
        self.dia_info = QLabel()
        self.dia_info.setObjectName("hint")
        f.addRow("", self.dia_info)
        lv.addWidget(g)

        # Coils & ends
        g = QGroupBox("Coils and ends")
        f = QFormLayout(g)
        self.end_type = QComboBox()
        self.end_type.addItems(END_TYPES)
        f.addRow("Ends", self.end_type)
        self.active = spin(0.5, 500, 2, 0.25)
        f.addRow("Active coils", self.active)
        self.total_info = QLabel()
        self.total_info.setObjectName("hint")
        f.addRow("", self.total_info)
        self.free_len = spin(0.001, 100000, 4, 0.05)
        f.addRow("Free length", self.free_len)
        self.hand = QComboBox()
        self.hand.addItems(["Right hand", "Left hand"])
        f.addRow("Wind", self.hand)
        lv.addWidget(g)

        # Rate solver
        g = QGroupBox("Design target")
        f = QFormLayout(g)
        self.target_form = f
        self.target_mode = QComboBox()
        self.target_mode.addItems(["Spring rate", "Force at a distance"])
        f.addRow("Target by", self.target_mode)
        self.target_k = spin(0.0001, 1e7, 4, 0.05)
        f.addRow("Target rate", self.target_k)
        self.target_F = spin(0.0001, 1e7, 3, 0.5)
        f.addRow("Force", self.target_F)
        self.target_x_kind = QComboBox()
        self.target_x_kind.addItems(["Deflection (travel)", "Compressed length"])
        self.target_x_kind.setToolTip("Deflection: distance compressed from free length.\n"
                                      "Compressed length: the spring's height at that force.")
        f.addRow("Distance as", self.target_x_kind)
        self.target_x = spin(0.0001, 100000, 4, 0.05)
        f.addRow("Distance", self.target_x)
        self.target_hint = QLabel()
        self.target_hint.setObjectName("hint")
        self.target_hint.setWordWrap(True)
        f.addRow(self.target_hint)
        brow = QHBoxLayout()
        b1 = QPushButton("Solve coils")
        b1.setToolTip("Change active coils to hit the target rate (wire and diameter fixed)")
        b1.clicked.connect(self.solve_coils)
        b2 = QPushButton("Solve wire Ø")
        b2.setToolTip("Change wire diameter to hit the target rate (coils and diameter fixed).\n"
                      "Snaps to the nearest standard size if 'snap' is checked.")
        b2.clicked.connect(self.solve_wire)
        brow.addWidget(b1)
        brow.addWidget(b2)
        f.addRow(brow)
        self.snap = QCheckBox("Snap wire to standard size")
        self.snap.setChecked(True)
        f.addRow(self.snap)
        self.solve_info = QLabel()
        self.solve_info.setObjectName("hint")
        self.solve_info.setWordWrap(True)
        f.addRow(self.solve_info)
        lv.addWidget(g)
        self.target_mode.currentIndexChanged.connect(self.on_target_mode)
        self.target_x_kind.currentIndexChanged.connect(self.on_target_x_kind)
        for w in (self.target_F, self.target_x):
            w.valueChanged.connect(self.update_target_hint)
            w.valueChanged.connect(self.solve_info.clear)
        self.on_target_mode(0)

        # Operating point
        g = QGroupBox("Operating point")
        f = QFormLayout(g)
        self.use_work = QCheckBox("Check force at a position")
        f.addRow(self.use_work)
        self.work_kind = QComboBox()
        self.work_kind.addItems(["Travel (compression)", "Working length"])
        self.work_kind.setToolTip("Travel: how far the spring is compressed from free length.\n"
                                  "Working length: the spring's compressed height.")
        self.work_kind.setEnabled(False)
        f.addRow("Check by", self.work_kind)
        self.work_len = spin(0.0, 100000, 4, 0.05)
        self.work_len.setEnabled(False)
        self.work_len_label = QLabel("Travel")
        f.addRow(self.work_len_label, self.work_len)
        lv.addWidget(g)
        lv.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(left)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(340)
        scroll.setMaximumWidth(420)
        splitter.addWidget(scroll)

        # ---- centre: preview ----
        self.tabs = QTabWidget()
        self.view3d = make_3d_view()
        self.drawing = SpringDrawing()
        if self.view3d is not None:
            self.tabs.addTab(self.view3d, "3D")
        self.tabs.addTab(self.drawing, "Drawing")
        self.chart = LoadChart()
        self.tabs.addTab(self.chart, "Load chart")
        splitter.addWidget(self.tabs)

        # ---- right: results ----
        right = QWidget()
        right.setObjectName("panel")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 16)
        rv.setSpacing(10)
        cards = QGridLayout()
        cards.setSpacing(8)
        self.card_k = MetricCard("Spring rate")
        self.card_solid = MetricCard("Solid height")
        self.card_force = MetricCard("Load at solid")
        self.card_stress = MetricCard("Stress at solid")
        cards.addWidget(self.card_k, 0, 0, 1, 2)
        cards.addWidget(self.card_solid, 1, 0)
        cards.addWidget(self.card_force, 1, 1)
        cards.addWidget(self.card_stress, 2, 0, 1, 2)
        rv.addLayout(cards)

        g = QGroupBox("Details")
        self.details = QFormLayout(g)
        self.details.setLabelAlignment(Qt.AlignLeft)
        self.detail_labels = {}
        for key in ["OD", "ID", "Mean diameter", "Spring index C", "Total coils", "Active pitch",
                    "Pitch angle", "Max deflection", "Stress correction Kb", "Wire Sut",
                    "Allowable (solid)", "OD at solid", "L₀ / D", "Natural freq.",
                    "Wire length", "Mass"]:
            v = QLabel("—")
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.details.addRow(key, v)
            self.detail_labels[key] = v
        rv.addWidget(g)

        self.work_box = QGroupBox("At operating point")
        wf = QFormLayout(self.work_box)
        self.work_labels = {}
        for key in ["Travel", "Length", "Force", "Stress", "% of allowable"]:
            v = QLabel("—")
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            wf.addRow(key, v)
            self.work_labels[key] = v
        rv.addWidget(self.work_box)
        self.work_box.setVisible(False)

        self.warn = QLabel()
        self.warn.setObjectName("warn")
        self.warn.setWordWrap(True)
        self.warn.setTextFormat(Qt.RichText)
        rv.addWidget(self.warn)
        rv.addStretch()

        rscroll = QScrollArea()
        rscroll.setWidgetResizable(True)
        rscroll.setFrameShape(QFrame.NoFrame)
        rscroll.setWidget(right)
        rscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rscroll.setMinimumWidth(320)
        rscroll.setMaximumWidth(400)
        splitter.addWidget(rscroll)
        splitter.setStretchFactor(1, 1)

        self.setStatusBar(QStatusBar())

        # ---- signals ----
        for w in (self.wire_d, self.dia_val, self.active, self.free_len, self.work_len):
            w.valueChanged.connect(self.on_input)
        for w in (self.material, self.end_type, self.hand):
            w.currentIndexChanged.connect(self.on_input)
        self.use_work.toggled.connect(self.on_work_toggled)
        self.work_kind.currentIndexChanged.connect(self.on_work_kind)
        self.dia_group.idToggled.connect(self.on_dia_mode)
        self.wire_std.activated.connect(self.on_std_wire)

    # ---------------- state <-> widgets ----------------
    def _apply_units_to_widgets(self):
        u = self.u
        dec = u.len_decimals
        step = 0.001 if u.imperial else 0.01
        for w in (self.wire_d, self.dia_val, self.free_len, self.work_len):
            w.blockSignals(True)
            w.setDecimals(dec)
            w.setSuffix(f"  {u.len_unit}")
            w.blockSignals(False)
        self.wire_d.setSingleStep(step)
        self.dia_val.setSingleStep(step * 10)
        self.free_len.setSingleStep(step * 50)
        self.work_len.setSingleStep(step * 50)
        self.target_k.setSuffix(f"  {u.rate_unit}")
        self.target_F.setSuffix(f"  {u.force_unit}")
        self.target_x.setSuffix(f"  {u.len_unit}")
        self.target_x.setDecimals(dec)
        self.target_x.setSingleStep(step * 50)
        self.wire_std.blockSignals(True)
        self.wire_std.clear()
        self.wire_std.addItem("Std…")
        sizes = WIRE_SIZES_IN if u.imperial else WIRE_SIZES_MM
        for v in sizes:
            self.wire_std.addItem(f"{v:.3f}" if u.imperial else f"{v:g}", v)
        self.wire_std.blockSignals(False)

    def _push_state_to_widgets(self):
        self._loading = True
        u, s = self.u, self.s
        self.wire_d.setValue(u.len(s.wire_d))
        self._set_dia_widget()
        self.active.setValue(s.active_coils)
        self.free_len.setValue(u.len(s.free_length))
        self.end_type.setCurrentText(s.end_type)
        self.material.setCurrentText(s.material)
        self.hand.setCurrentIndex(0 if s.right_hand else 1)
        self.use_work.setChecked(s.work_length is not None)
        self.work_len.setEnabled(s.work_length is not None)
        self.work_kind.setEnabled(s.work_length is not None)
        self._set_work_position(s.work_length if s.work_length is not None else s.free_length * 0.8)
        if self.target_k.value() <= 0.0001:
            self.target_k.setValue(u.rate(compute(s).rate or 1))
        if self.target_F.value() <= 0.0001:
            r0 = compute(s)
            x0 = max((s.free_length - (r0.solid_length or 0)) * 0.5, s.free_length * 0.1)
            self.target_F.setValue(u.force((r0.rate or 1) * x0))
            self.target_x_kind.setCurrentIndex(0)
            self.target_x.setValue(u.len(x0))
        self._loading = False

    def _set_dia_widget(self):
        mode = self.dia_group.checkedId()
        s = self.s
        val = [s.od, s.id, s.mean_d][mode]
        self.dia_label.setText(["OD", "ID", "Mean Ø"][mode])
        self.dia_val.blockSignals(True)
        self.dia_val.setValue(self.u.len(val))
        self.dia_val.blockSignals(False)

    def _read_widgets(self):
        u = self.u
        d = u.len_in(self.wire_d.value())
        v = u.len_in(self.dia_val.value())
        mode = self.dia_group.checkedId()
        mean = v - d if mode == 0 else v + d if mode == 1 else v
        self.s = SpringInput(
            wire_d=d, mean_d=mean, active_coils=self.active.value(),
            free_length=u.len_in(self.free_len.value()),
            end_type=self.end_type.currentText(), material=self.material.currentText(),
            right_hand=self.hand.currentIndex() == 0,
            work_length=self._work_length_from_widget(u.len_in(self.free_len.value()))
            if self.use_work.isChecked() else None,
        )

    # ---------------- slots ----------------
    def on_input(self, *_):
        if self._loading:
            return
        self._read_widgets()
        self.timer.start()

    def on_work_toggled(self, on):
        self.work_len.setEnabled(on)
        self.work_kind.setEnabled(on)
        if on and not self._loading:
            r = self.r
            if r.ok:
                self._set_work_position((self.s.free_length + r.solid_length) / 2)
        self.on_input()

    def _work_is_travel(self):
        return self.work_kind.currentIndex() == 0

    def _work_length_from_widget(self, free_length_mm):
        """Compressed length (mm) described by the operating-point box."""
        v = self.u.len_in(self.work_len.value())
        return free_length_mm - v if self._work_is_travel() else v

    def _set_work_position(self, length_mm):
        """Show a compressed length (mm) in the box, as travel or length per the selector."""
        v = self.s.free_length - length_mm if self._work_is_travel() else length_mm
        self.work_len.blockSignals(True)
        self.work_len.setValue(self.u.len(max(v, 0.0)))
        self.work_len.blockSignals(False)

    def on_work_kind(self, idx):
        # same spring position, expressed the other way: travel <-> length = L0 - value
        L0 = self.u.len_in(self.free_len.value())
        v = self.u.len_in(self.work_len.value())
        self.work_len_label.setText("Travel" if idx == 0 else "Working length")
        self.work_len.blockSignals(True)
        self.work_len.setValue(self.u.len(max(L0 - v, 0.0)))
        self.work_len.blockSignals(False)
        self.on_input()

    def on_dia_mode(self, _id, checked):
        if checked:
            self._set_dia_widget()

    def on_std_wire(self, idx):
        if idx <= 0:
            return
        val = self.wire_std.itemData(idx)
        self.wire_std.setCurrentIndex(0)
        self.wire_d.setValue(val)

    def on_units_changed(self, idx):
        self._read_widgets()
        k_target = self.u.rate_in(self.target_k.value())
        F_target = self.u.force_in(self.target_F.value())
        x_target = self.u.len_in(self.target_x.value())
        self.u = Units(idx)
        self.settings.setValue("units_system", idx)
        self._apply_units_to_widgets()
        self._push_state_to_widgets()
        self.target_k.setValue(self.u.rate(k_target))
        self.target_F.setValue(self.u.force(F_target))
        self.target_x.setValue(self.u.len(x_target))
        self.recompute()

    def solve_coils(self):
        self._read_widgets()
        s = self.s
        k = self._target_rate()
        if k is None:
            return
        G = MATERIALS[s.material]["G"]
        na = active_coils_for_rate(G, s.wire_d, s.mean_d, k)
        na_r = max(0.5, round(na * 4) / 4)   # quarter turns
        self.active.setValue(na_r)
        self.solve_info.setText(f"Exact: {na:.3f} active coils → rounded to {na_r:g}." + self._after_solve())

    def solve_wire(self):
        self._read_widgets()
        s = self.s
        k = self._target_rate()
        if k is None:
            return
        G = MATERIALS[s.material]["G"]
        mode = self.dia_group.checkedId()
        # Keep the diameter the user set by (OD/ID/mean) fixed: iterate since D depends on d
        d = s.wire_d
        for _ in range(60):
            D = s.mean_d if mode == 2 else (s.od - d if mode == 0 else s.id + d)
            d_new = wire_d_for_rate(G, D, s.active_coils, k)
            if abs(d_new - d) < 1e-9:
                break
            d = d_new
        exact = d
        if self.snap.isChecked():
            sizes = WIRE_SIZES_IN if self.u.imperial else WIRE_SIZES_MM
            d_disp = min(sizes, key=lambda v: abs(self.u.len_in(v) - exact))
            d = self.u.len_in(d_disp)
        self.wire_d.setValue(self.u.len(d))
        txt = f"Exact: {self.u.fl(exact)}"
        if self.snap.isChecked():
            txt += f" → standard {self.u.fl(d)}"
        self.solve_info.setText(txt + "." + self._after_solve())

    # ---------------- design target ----------------
    def on_target_mode(self, mode):
        by_force = mode == 1
        f = self.target_form
        f.setRowVisible(self.target_k, not by_force)
        for w in (self.target_F, self.target_x_kind, self.target_x, self.target_hint):
            f.setRowVisible(w, by_force)
        self.solve_info.clear()
        self.update_target_hint()

    def on_target_x_kind(self, kind):
        # convert the number so it describes the same spring position
        self._read_widgets()
        x = self.u.len_in(self.target_x.value())
        other = self.s.free_length - x
        if other > 0:
            self.target_x.setValue(self.u.len(other))
        self.update_target_hint()

    def _target_deflection(self):
        """Deflection from free length for the force target, in mm (None if invalid)."""
        x = self.u.len_in(self.target_x.value())
        if self.target_x_kind.currentIndex() == 1:
            x = self.s.free_length - x
        return x if x > 0 else None

    def _target_rate(self):
        """Target spring rate in N/mm, or None (with a message) if the inputs don't work."""
        self._read_widgets()
        if self.target_mode.currentIndex() == 0:
            return self.u.rate_in(self.target_k.value())
        x = self._target_deflection()
        if x is None:
            self.solve_info.setText("Compressed length must be shorter than the free length.")
            return None
        return self.u.force_in(self.target_F.value()) / x

    def update_target_hint(self, *_):
        if self._loading or self.target_mode.currentIndex() != 1:
            return
        self._read_widgets()
        x = self._target_deflection()
        if x is None:
            self.target_hint.setText("<span style='color:#e5675b'>Compressed length must be "
                                     "shorter than the free length.</span>")
            return
        u = self.u
        k = u.force_in(self.target_F.value()) / x
        txt = f"Required rate: <b>{u.fr(k)}</b>"
        if self.target_x_kind.currentIndex() == 0:
            txt += f"  ·  at length {u.fl(self.s.free_length - x)}"
        else:
            txt += f"  ·  deflection {u.fl(x)}"
        r = compute(self.s)
        if r.ok and self.s.free_length - x < r.solid_length:
            txt += ("<br><span style='color:#e3b341'>That position is below the current solid "
                    f"height ({u.fl(r.solid_length)}).</span>")
        self.target_hint.setText(txt)

    def _after_solve(self):
        """In force mode: show the operating point and report the force actually achieved."""
        if self.target_mode.currentIndex() != 1:
            return ""
        self._read_widgets()
        x = self._target_deflection()
        if x is None:
            return ""
        u = self.u
        self.use_work.setChecked(True)          # check first: toggling on resets the length
        self._set_work_position(self.s.free_length - x)
        self._read_widgets()
        r = compute(self.s)
        self.recompute()
        if not r.ok:
            return ""
        F_goal = u.force_in(self.target_F.value())
        F_got = r.rate * x
        return (f"\nGives {u.ff(F_got)} at that distance "
                f"({(F_got / F_goal - 1) * 100:+.1f}% vs target).")

    # ---------------- compute & display ----------------
    def recompute(self):
        self.update_target_hint()   # free length / solid height may have changed
        self._read_widgets()
        s, u = self.s, self.u
        r = self.r = compute(s)

        mat = MATERIALS[s.material]
        g_txt = (f"{u.stress(mat['G']) / 1000:,.1f} Mpsi" if u.imperial
                 else f"{u.stress(mat['G']):,.0f} {u.stress_unit}")
        self.mat_info.setText(f"G = {g_txt}   ·   "
                              f"allow {mat['allow'] * 100:.0f}% Sut")
        mode = self.dia_group.checkedId()
        others = [("OD", s.od), ("ID", s.id), ("Mean", s.mean_d)]
        others.pop(mode)
        self.dia_info.setText("   ·   ".join(f"{n} {u.fl(v)}" for n, v in others))
        self.total_info.setText(f"{r.total_coils:g} total coils" if r.ok or r.total_coils else "")

        if r.errors and r.rate == 0:
            for c in (self.card_k, self.card_solid, self.card_force, self.card_stress):
                c.set("—")
            self.warn.setText("<br>".join(f"<b>✕</b> {e}" for e in r.errors))
            self.drawing.set_spring(s, r, u.fl)
            self.chart.set_spring(s, r, u)
            return

        self.card_k.set(u.fr(r.rate), "k = G·d⁴ / (8·D³·Na)")
        self.card_solid.set(u.fl(r.solid_length), f"travel {u.fl(r.max_deflection)}")
        self.card_force.set(u.ff(r.force_solid), "")
        ratio = r.stress_solid / r.allow if r.allow else 0
        state = "bad" if ratio > 1 else "warn" if ratio > 0.85 else "good"
        self.card_stress.set(u.fs(r.stress_solid),
                             f"{ratio * 100:.0f}% of allowable {u.fs(r.allow)}  ·  "
                             f"safety factor {r.safety_solid:.2f}", state)

        D = self.detail_labels
        D["OD"].setText(u.fl(s.od))
        D["ID"].setText(u.fl(s.id))
        D["Mean diameter"].setText(u.fl(s.mean_d))
        D["Spring index C"].setText(f"{r.index:.2f}")
        D["Total coils"].setText(f"{r.total_coils:g}")
        D["Active pitch"].setText(u.fl(r.pitch))
        D["Pitch angle"].setText(f"{r.pitch_angle_deg:.2f}°")
        D["Max deflection"].setText(u.fl(r.max_deflection))
        D["Stress correction Kb"].setText(f"{r.bergstrasser:.3f}")
        D["Wire Sut"].setText(u.fs(r.sut))
        D["Allowable (solid)"].setText(u.fs(r.allow))
        D["OD at solid"].setText(u.fl(r.od_solid))
        D["L₀ / D"].setText(f"{r.slenderness:.2f}  (limit {r.buckling_limit:.2f})")
        D["Natural freq."].setText(f"{r.nat_freq:,.0f} Hz")
        D["Wire length"].setText(u.fl(r.wire_length))
        D["Mass"].setText(f"{u.mass(r.mass):.3f} {u.mass_unit}")

        if s.work_length is not None and r.work_force is not None:
            self.work_box.setVisible(True)
            W = self.work_labels
            W["Travel"].setText(u.fl(r.work_deflection))
            W["Length"].setText(u.fl(s.work_length))
            W["Force"].setText(u.ff(r.work_force))
            W["Stress"].setText(u.fs(r.work_stress))
            W["% of allowable"].setText(f"{r.work_stress / r.allow * 100:.0f}%")
        else:
            self.work_box.setVisible(False)

        msgs = [f"<span style='color:#e5675b'><b>✕</b> {e}</span>" for e in r.errors]
        msgs += [f"<span style='color:#e3b341'><b>!</b> {w}</span>" for w in r.warnings]
        if not msgs:
            msgs = ["<span style='color:#6fbf73'>✓ No design issues found.</span>"]
        self.warn.setText("<br><br>".join(msgs))

        self.step_action.setEnabled(r.ok)
        self.stl_action.setEnabled(r.ok)

        if r.ok:
            if self.view3d is not None:
                try:
                    self.view3d.update_spring(s)
                except Exception:
                    pass
        self.drawing.set_spring(s, r, u.fl)
        self.chart.set_spring(s, r, u)
        title = APP_NAME + (f" — {self.current_path}" if self.current_path else "")
        self.setWindowTitle(title)

    # ---------------- files ----------------
    def new_design(self):
        self.s = SpringInput(wire_d=0.080 * MM_PER_IN, mean_d=(0.750 - 0.080) * MM_PER_IN,
                             active_coils=8, free_length=2.0 * MM_PER_IN)
        self.current_path = None
        self._push_state_to_widgets()
        self.recompute()

    def save_design(self):
        self._read_widgets()
        path, _ = QFileDialog.getSaveFileName(self, "Save design", self._default_name("spring"),
                                              "Spring design (*.spring.json *.json)")
        if not path:
            return
        data = {"app": APP_NAME, "version": VERSION, "units_mm_N": True, "spring": self.s.to_dict()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.current_path = path
        self.statusBar().showMessage(f"Saved {path}", 5000)
        self.recompute()

    def open_design(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open design", "",
                                              "Spring design (*.spring.json *.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.s = SpringInput.from_dict(data["spring"])
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Could not open file:\n{e}")
            return
        self.current_path = path
        self._push_state_to_widgets()
        self.recompute()

    def _default_name(self, ext):
        s, u = self.s, self.u
        return (f"spring_{u.len(s.wire_d):.3f}x{u.len(s.od):.3f}OD_"
                f"{u.len(s.free_length):.3f}L_{u.len_unit}.{ext}").replace("..", ".")

    def export(self, kind):
        self._read_widgets()
        if not compute(self.s).ok:
            return
        ext = "step" if kind == "step" else "stl"
        filt = "STEP file (*.step *.stp)" if kind == "step" else "STL mesh (*.stl)"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {ext.upper()}", self._default_name(ext), filt)
        if not path:
            return
        if not path.lower().endswith((".step", ".stp", ".stl")):
            path += "." + ext
        self.statusBar().showMessage(f"Building {ext.upper()} solid…")
        QApplication.setOverrideCursor(Qt.BusyCursor)
        job = ExportJob(self.s, path, kind)
        job.signals.done.connect(self._export_done)
        job.signals.failed.connect(self._export_failed)
        self._job = job
        self.pool.start(job)

    def _export_done(self, path):
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"Exported {path}  (geometry in mm)", 8000)

    def _export_failed(self, tb):
        QApplication.restoreOverrideCursor()
        self.statusBar().clearMessage()
        QMessageBox.critical(self, APP_NAME, "Export failed:\n\n" + tb[-1500:])

    def copy_spec(self):
        self._read_widgets()
        s, r, u = self.s, compute(self.s), self.u
        lines = [
            "COMPRESSION SPRING SPECIFICATION",
            f"Material:        {s.material}",
            f"Wire diameter:   {u.fl(s.wire_d)}",
            f"Outside dia:     {u.fl(s.od)}",
            f"Inside dia:      {u.fl(s.id)}",
            f"Free length:     {u.fl(s.free_length)}",
            f"Active coils:    {s.active_coils:g}",
            f"Total coils:     {r.total_coils:g}",
            f"Ends:            {s.end_type}",
            f"Wind:            {'Right hand' if s.right_hand else 'Left hand'}",
            f"Rate:            {u.fr(r.rate)}",
            f"Solid height:    {u.fl(r.solid_length)}",
            f"Load at solid:   {u.ff(r.force_solid)}",
            f"Stress at solid: {u.fs(r.stress_solid)}  (allow {u.fs(r.allow)})",
        ]
        if s.work_length is not None:
            lines.append(f"Load at {u.fl(s.work_length)} (travel {u.fl(r.work_deflection)}): "
                         f"{u.ff(r.work_force)}")
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage("Specification copied to clipboard", 4000)


STYLE = """
* { font-size: 10pt; }
QMainWindow, QWidget { background: #14171b; color: #d6dce2; }
QWidget#panel { background: #14171b; }
QToolBar { background: #101317; border: none; border-bottom: 1px solid #262b31; padding: 6px 10px; spacing: 6px; }
QToolBar QToolButton { padding: 6px 12px; border-radius: 6px; color: #d6dce2; }
QToolBar QToolButton:hover { background: #22272e; }
QToolBar QToolButton:disabled { color: #59626b; }
QToolButton#primary { background: #d98a2b; color: #15110b; font-weight: 600; }
QToolButton#primary:hover { background: #e89a3c; }
QToolButton#primary:disabled { background: #3a3128; color: #7b6d5c; }
QGroupBox { border: 1px solid #262b31; border-radius: 8px; margin-top: 14px; padding: 12px 10px 10px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8f9aa5; }
QLabel { background: transparent; font-weight: normal; }
QLabel#hint { color: #7d8893; font-size: 9pt; }
QLabel#warn { padding: 10px; background: #191d22; border-radius: 8px; }
QDoubleSpinBox, QComboBox { background: #1d2228; border: 1px solid #2c333b; border-radius: 6px; padding: 5px 8px; min-height: 20px; selection-background-color: #d98a2b; }
QDoubleSpinBox:focus, QComboBox:focus { border-color: #d98a2b; }
QDoubleSpinBox:disabled { color: #5c656e; }
QComboBox QAbstractItemView { background: #1d2228; border: 1px solid #2c333b; selection-background-color: #2f3640; }
QPushButton { background: #232930; border: 1px solid #323a43; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { border-color: #d98a2b; }
QPushButton:pressed { background: #2c333b; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #2c333b; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; padding: 8px 18px; color: #8f9aa5; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #e8ecef; border-bottom: 2px solid #d98a2b; }
QFrame#card { background: #1a1f25; border: 1px solid #262b31; border-radius: 10px; }
QLabel#cardTitle { color: #7d8893; font-size: 8pt; letter-spacing: 1px; }
QLabel#cardValue { font-size: 17pt; font-weight: 600; color: #eef1f4; }
QLabel#cardValue[state="good"] { color: #6fbf73; }
QLabel#cardValue[state="warn"] { color: #e3b341; }
QLabel#cardValue[state="bad"] { color: #e5675b; }
QLabel#cardSub { color: #7d8893; font-size: 8.5pt; }
QSplitter::handle { background: #262b31; }
QStatusBar { background: #101317; color: #8f9aa5; }
QScrollArea { background: #14171b; }
"""


def main():
    # Headless self-test: CoilSpringDesigner --selftest out.step
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        from .geometry import export_step
        s = SpringInput()
        sol = export_step(s, sys.argv[2])
        print(f"selftest ok: k={compute(s).rate:.3f} N/mm valid={sol.isValid()} -> {sys.argv[2]}")
        return
    QApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
