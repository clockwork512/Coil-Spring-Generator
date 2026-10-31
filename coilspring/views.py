"""Preview widgets: 3D view, 2D drawing, load chart."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QBrush
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

from .calc import SpringInput, SpringResult
from .geometry import tube_mesh, centerline

ACCENT = QColor("#d98a2b")
WIRE = QColor("#9fb4c7")
INK = QColor("#cfd6dd")
DIM = QColor("#7c8a97")
BG = QColor("#1b1f24")


# ---------------------------------------------------------------------------
# 3D
# ---------------------------------------------------------------------------
def make_3d_view(parent=None):
    """Return a 3D view widget, or None if OpenGL isn't available."""
    try:
        import pyqtgraph.opengl as gl  # noqa: F401
    except Exception:
        return None
    try:
        return Spring3DView(parent)
    except Exception:
        return None


class Spring3DView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        import pyqtgraph.opengl as gl
        self._gl = gl
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = gl.GLViewWidget()
        self.view.setBackgroundColor(BG)
        lay.addWidget(self.view)
        self.mesh = None
        self.plates = []
        self.grid = gl.GLGridItem()
        self.grid.setColor((255, 255, 255, 25))
        self.view.addItem(self.grid)
        self._last_size = None

    def update_spring(self, s: SpringInput):
        gl = self._gl
        verts, faces, normals = tube_mesh(s)
        verts = verts.copy()
        verts[:, 2] -= s.free_length / 2
        # Baked lighting: key light from upper front, fill from the side, plus ambient
        def L(v):
            v = np.asarray(v, float)
            return v / np.linalg.norm(v)
        key = np.clip(normals @ L((0.8, 0.6, 0.9)), 0, None)
        fill = np.clip(normals @ L((-0.7, -0.3, 0.2)), 0, None)
        rim = np.clip(normals @ L((0.0, 0.0, 1.0)), 0, None) ** 4
        shade = np.clip(0.28 + 0.62 * key + 0.22 * fill + 0.25 * rim, 0, 1.15)
        base = np.array([0.66, 0.74, 0.82])
        cols = np.ones((len(verts), 4), np.float32)
        cols[:, :3] = np.clip(shade[:, None] * base[None, :], 0, 1)
        md = gl.MeshData(vertexes=verts, faces=faces, vertexColors=cols)
        if self.mesh is None:
            self.mesh = gl.GLMeshItem(meshdata=md, smooth=True, shader=None, glOptions="opaque")
            self.view.addItem(self.mesh)
        else:
            self.mesh.setMeshData(meshdata=md, smooth=True)

        size = max(s.free_length, s.od)
        self.grid.resetTransform()
        step = 10 ** math.floor(math.log10(max(s.od, 1e-3)))
        self.grid.setSpacing(step, step)
        self.grid.setSize(s.od * 2.5, s.od * 2.5)
        self.grid.translate(0, 0, -s.free_length / 2)
        if self._last_size is None or abs(size - self._last_size) / self._last_size > 0.25:
            self.view.setCameraPosition(distance=size * 1.6, elevation=18, azimuth=35)
            self.view.opts["center"] = self.view.opts["center"] * 0
            self._last_size = size


# ---------------------------------------------------------------------------
# 2D side drawing with dimensions
# ---------------------------------------------------------------------------
class SpringDrawing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.s: SpringInput | None = None
        self.r: SpringResult | None = None
        self.fmt_len = lambda v: f"{v:.2f}"
        self.setMinimumSize(300, 300)

    def set_spring(self, s, r, fmt_len):
        self.s, self.r, self.fmt_len = s, r, fmt_len
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BG)
        if not self.s or not self.r or not self.r.ok:
            p.setPen(DIM)
            p.drawText(self.rect(), Qt.AlignCenter, "Enter a valid spring")
            return
        s = self.s
        W, H = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 70, 150, 80, 70
        aw, ah = W - margin_l - margin_r, H - margin_t - margin_b
        sc = min(aw / s.od, ah / s.free_length)
        cx = margin_l + aw / 2
        z0 = margin_t + (ah + s.free_length * sc) / 2   # screen y of z=0

        def X(x):
            return cx + x * sc

        def Y(z):
            return z0 - z * sc

        pts, *_ = centerline(s, 48)
        ground = "ground" in s.end_type
        lw = s.wire_d * sc

        # clip region for ground ends
        if ground:
            p.save()
            p.setClipRect(QRectF(0, Y(s.free_length), W, s.free_length * sc))

        # back half first (y > 0 is "behind"), then front half
        for front in (False, True):
            col = WIRE if front else WIRE.darker(180)
            pen = QPen(col, max(lw, 1.0), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            path = QPainterPath()
            drawing = False
            for x, y, z in pts:
                is_front = y <= 0
                if is_front == front:
                    if not drawing:
                        path.moveTo(X(x), Y(z))
                        drawing = True
                    else:
                        path.lineTo(X(x), Y(z))
                else:
                    drawing = False
            p.drawPath(path)
            if front:
                # thin highlight
                p.setPen(QPen(col.lighter(135), max(lw * 0.25, 0.6), Qt.SolidLine, Qt.RoundCap))
                p.drawPath(path.translated(-lw * 0.18, -lw * 0.18))
        if ground:
            p.restore()

        # end plates
        p.setPen(QPen(DIM, 1, Qt.DashLine))
        p.drawLine(QPointF(X(-s.od * 0.75), Y(0)), QPointF(X(s.od * 0.75), Y(0)))
        p.drawLine(QPointF(X(-s.od * 0.75), Y(s.free_length)), QPointF(X(s.od * 0.75), Y(s.free_length)))
        # axis
        p.setPen(QPen(DIM.darker(130), 1, Qt.DashDotLine))
        p.drawLine(QPointF(cx, Y(-s.free_length * 0.05)), QPointF(cx, Y(s.free_length * 1.05)))

        # dimensions
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        dim_pen = QPen(ACCENT, 1)

        def hdim(x1, x2, y, text, above):
            p.setPen(dim_pen)
            p.drawLine(QPointF(x1, y), QPointF(x2, y))
            for xx, sgn in ((x1, 1), (x2, -1)):
                p.drawLine(QPointF(xx, y), QPointF(xx + 6 * sgn, y - 3))
                p.drawLine(QPointF(xx, y), QPointF(xx + 6 * sgn, y + 3))
            p.setPen(INK)
            r = QRectF(min(x1, x2), y - 20 if above else y + 3, abs(x2 - x1), 16)
            p.drawText(r, Qt.AlignCenter, text)

        def vdim(x, y1, y2, text):
            p.setPen(dim_pen)
            p.drawLine(QPointF(x, y1), QPointF(x, y2))
            for yy, sgn in ((y1, 1), (y2, -1)):
                p.drawLine(QPointF(x, yy), QPointF(x - 3, yy + 6 * sgn))
                p.drawLine(QPointF(x, yy), QPointF(x + 3, yy + 6 * sgn))
            p.setPen(INK)
            p.drawText(QRectF(x + 8, (y1 + y2) / 2 - 9, 140, 18), Qt.AlignLeft | Qt.AlignVCenter, text)

        # OD above
        y_od = Y(s.free_length) - 22
        p.setPen(QPen(DIM, 1))
        p.drawLine(QPointF(X(-s.od / 2), Y(s.free_length) - 4), QPointF(X(-s.od / 2), y_od - 4))
        p.drawLine(QPointF(X(s.od / 2), Y(s.free_length) - 4), QPointF(X(s.od / 2), y_od - 4))
        hdim(X(-s.od / 2), X(s.od / 2), y_od, f"OD {self.fmt_len(s.od)}", True)
        # ID below
        y_id = Y(0) + 26
        p.setPen(QPen(DIM, 1))
        p.drawLine(QPointF(X(-s.id / 2), Y(0) + 4), QPointF(X(-s.id / 2), y_id + 4))
        p.drawLine(QPointF(X(s.id / 2), Y(0) + 4), QPointF(X(s.id / 2), y_id + 4))
        hdim(X(-s.id / 2), X(s.id / 2), y_id, f"ID {self.fmt_len(s.id)}", False)
        # free length right
        xr = X(s.od / 2) + 28
        p.setPen(QPen(DIM, 1))
        p.drawLine(QPointF(X(s.od * 0.75) + 2, Y(0)), QPointF(xr + 4, Y(0)))
        p.drawLine(QPointF(X(s.od * 0.75) + 2, Y(s.free_length)), QPointF(xr + 4, Y(s.free_length)))
        vdim(xr, Y(s.free_length), Y(0), f"L₀ {self.fmt_len(s.free_length)}")
        # solid length
        xs = xr + 0  # stacked text
        p.setPen(DIM)
        p.drawText(QRectF(xs + 8, Y(0) - 40, 140, 18), Qt.AlignLeft,
                   f"Ls {self.fmt_len(self.r.solid_length)}")
        # wire dia label
        p.setPen(INK)
        p.drawText(QRectF(8, 8, W - 16, 18), Qt.AlignLeft,
                   f"Ø wire {self.fmt_len(s.wire_d)}   ·   {s.end_type}   ·   "
                   f"{'RH' if s.right_hand else 'LH'}   ·   {self.r.total_coils:g} total / {s.active_coils:g} active coils")


# ---------------------------------------------------------------------------
# Load chart
# ---------------------------------------------------------------------------
class LoadChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        import pyqtgraph as pg
        self.pg = pg
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        pg.setConfigOptions(antialias=True)
        self.plot = pg.PlotWidget(background=BG)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.invertX(True)
        lay.addWidget(self.plot)
        self.curve = self.plot.plot(pen=pg.mkPen(WIRE, width=2.5))
        self.allow_line = pg.InfiniteLine(angle=0, pen=pg.mkPen(ACCENT, width=1, style=Qt.DashLine),
                                          label="allowable", labelOpts=dict(color=ACCENT, position=0.9))
        self.plot.addItem(self.allow_line)
        self.solid_line = pg.InfiniteLine(angle=90, pen=pg.mkPen(DIM, width=1, style=Qt.DashLine),
                                          label="solid", labelOpts=dict(color=DIM, position=0.5, anchors=[(0, 0.5), (0, 0.5)]))
        self.plot.addItem(self.solid_line)
        self.work = pg.ScatterPlotItem(size=10, brush=pg.mkBrush(ACCENT), pen=None)
        self.plot.addItem(self.work)

    def set_spring(self, s, r, u):
        """u: units helper with .len(), .force(), labels."""
        if not r.ok:
            self.curve.setData([], [])
            self.work.setData([], [])
            return
        L = np.linspace(s.free_length, r.solid_length, 50)
        F = r.rate * (s.free_length - L)
        self.curve.setData(u.len_arr(L), u.force_arr(F))
        # force at which allowable stress is reached
        f_allow = r.allow * math.pi * s.wire_d**3 / (r.bergstrasser * 8 * s.mean_d)
        self.allow_line.setValue(u.force(f_allow))
        self.solid_line.setValue(u.len(r.solid_length))
        if s.work_length is not None and r.work_force is not None:
            self.work.setData([u.len(s.work_length)], [u.force(r.work_force)])
        else:
            self.work.setData([], [])
        self.plot.setLabel("bottom", f"Length ({u.len_unit})")
        self.plot.setLabel("left", f"Force ({u.force_unit})")
        top = max(u.force(r.force_solid), u.force(f_allow)) * 1.1
        self.plot.setYRange(0, top, padding=0)
        self.plot.setXRange(u.len(r.solid_length) * 0.95, u.len(s.free_length) * 1.02, padding=0)
