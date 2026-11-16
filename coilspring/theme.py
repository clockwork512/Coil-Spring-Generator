"""Colour themes. Everything that draws reads its colours from here.

To tweak a colour, change it in DARK or LIGHT below.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

DARK = dict(
    bg="#14171b", bar="#101317", border="#262b31",
    field="#1d2228", field_ro="#171b20", field_border="#2c333b",
    hover="#22272e", pressed="#2c333b", button="#232930", button_border="#323a43",
    text="#d6dce2", text_strong="#eef1f4", muted="#8f9aa5", hint="#7d8893", disabled="#5c656e",
    ro_text="#a9b4be", card="#1a1f25", warnbox="#191d22", scroll="#2c333b",
    accent="#d98a2b", accent_hover="#e89a3c", accent_text="#15110b",
    accent_dis_bg="#3a3128", accent_dis_fg="#7b6d5c",
    good="#6fbf73", warn="#e3b341", bad="#e5675b", check_border="#8b97a3",
    code_bg="#0f1215", code_text="#c9d3dc",
    plot_bg="#1b1f24", wire="#9fb4c7", ink="#cfd6dd", dim="#7c8a97", axis="#8f9aa5",
    grid=(255, 255, 255, 25), band=(217, 138, 43, 40), mesh=(0.66, 0.74, 0.82),
)

LIGHT = dict(
    bg="#f3f4f6", bar="#ffffff", border="#d8dce1",
    field="#ffffff", field_ro="#eceef1", field_border="#c5ccd3",
    hover="#e8ebef", pressed="#dce0e5", button="#ffffff", button_border="#c5ccd3",
    text="#1f252b", text_strong="#0e1215", muted="#56616c", hint="#67727d", disabled="#a2aab2",
    ro_text="#4a545e", card="#ffffff", warnbox="#ffffff", scroll="#c5ccd3",
    accent="#c06c12", accent_hover="#a95d0c", accent_text="#ffffff",
    accent_dis_bg="#ecdfcd", accent_dis_fg="#a8977f",
    good="#23843b", warn="#9a6b00", bad="#c13b2a", check_border="#7d8893",
    code_bg="#f7f8fa", code_text="#1f252b",
    plot_bg="#ffffff", wire="#56748d", ink="#26303a", dim="#7a8792", axis="#4f5a65",
    grid=(0, 0, 0, 30), band=(192, 108, 18, 45), mesh=(0.56, 0.64, 0.72),
)

THEMES = {"Dark": DARK, "Light": LIGHT}

# The active palette. Updated in place so modules that imported it see changes.
T: dict = dict(DARK)
current_name = "Dark"


def set_theme(name: str):
    global current_name
    current_name = name if name in THEMES else "Dark"
    T.clear()
    T.update(THEMES[current_name])


def is_dark() -> bool:
    return current_name == "Dark"


def c(key: str) -> QColor:
    """A palette colour as a QColor."""
    v = T[key]
    return QColor(*v) if isinstance(v, tuple) else QColor(v)


def blend(a: QColor, b: QColor, t: float) -> QColor:
    """Mix colour a toward b by fraction t."""
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def qpalette() -> QPalette:
    """Qt palette, so checkboxes, radio buttons and pop-ups match the theme."""
    p = QPalette()
    p.setColor(QPalette.Window, c("bg"))
    p.setColor(QPalette.WindowText, c("text"))
    p.setColor(QPalette.Base, c("field"))
    p.setColor(QPalette.AlternateBase, c("card"))
    p.setColor(QPalette.Text, c("text"))
    p.setColor(QPalette.Button, c("button"))
    p.setColor(QPalette.ButtonText, c("text"))
    p.setColor(QPalette.Highlight, c("accent"))
    p.setColor(QPalette.HighlightedText, c("accent_text"))
    p.setColor(QPalette.ToolTipBase, c("card"))
    p.setColor(QPalette.ToolTipText, c("text"))
    p.setColor(QPalette.PlaceholderText, c("hint"))
    p.setColor(QPalette.Mid, c("field_border"))
    p.setColor(QPalette.Dark, c("border"))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c("disabled"))
    return p


def span(kind: str, html: str) -> str:
    """Coloured rich-text snippet: kind is 'good', 'warn' or 'bad'."""
    return f"<span style='color:{T[kind]}'>{html}</span>"


_STYLE = """
* {{ font-size: 10pt; }}
QMainWindow, QWidget {{ background: {bg}; color: {text}; }}
QWidget#panel {{ background: {bg}; }}
QToolTip {{ background: {card}; color: {text}; border: 1px solid {border}; padding: 4px; }}
QToolBar {{ background: {bar}; border: none; border-bottom: 1px solid {border}; padding: 6px 10px; spacing: 6px; }}
QToolBar QToolButton {{ padding: 6px 12px; border-radius: 6px; color: {text}; background: transparent; }}
QToolBar QLabel, QWidget#spacer {{ background: transparent; }}
QToolBar QToolButton:hover {{ background: {hover}; }}
QToolBar QToolButton:disabled {{ color: {disabled}; }}
QToolButton#primary {{ background: {accent}; color: {accent_text}; font-weight: 600; }}
QToolButton#primary:hover {{ background: {accent_hover}; }}
QToolButton#primary:disabled {{ background: {accent_dis_bg}; color: {accent_dis_fg}; }}
QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 14px; padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {muted}; }}
QLabel {{ background: transparent; font-weight: normal; }}
QLabel#hint {{ color: {hint}; font-size: 9pt; }}
QLabel#warn {{ padding: 10px; background: {warnbox}; border: 1px solid {border}; border-radius: 8px; }}
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {{ background: {field}; color: {text}; border: 1px solid {field_border}; border-radius: 6px; padding: 5px 8px; min-height: 20px; selection-background-color: {accent}; selection-color: {accent_text}; }}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
QDoubleSpinBox:disabled {{ color: {disabled}; }}
QDoubleSpinBox[readOnly="true"] {{ background: {field_ro}; color: {ro_text}; border-style: dashed; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 18px; border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {hover}; }}
QAbstractSpinBox::up-arrow {{ image: url({icon_up}); width: 8px; height: 5px; }}
QAbstractSpinBox::down-arrow {{ image: url({icon_down}); width: 8px; height: 5px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::down-arrow:disabled {{ image: none; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url({icon_down}); width: 8px; height: 5px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 2px solid {check_border}; background: {field}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({icon_check}); }}
QRadioButton::indicator:checked {{ border-color: {accent}; image: url({icon_dot}); }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {disabled}; background: transparent; }}
QToolButton#devbtn {{ color: {accent}; font-weight: 700; font-style: italic; border: none; background: transparent; padding: 0 5px; border-radius: 4px; }}
QToolButton#devbtn:hover {{ background: {hover}; }}
QTreeWidget, QTextBrowser, QPlainTextEdit {{ background: {field}; color: {text}; border: 1px solid {field_border}; border-radius: 6px; }}
QTreeWidget::item {{ padding: 2px 0; }}
QTreeWidget::item:selected {{ background: {hover}; color: {text_strong}; }}
QHeaderView::section {{ background: {bar}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 4px 6px; }}
QDockWidget {{ color: {muted}; font-weight: 600; }}
QDockWidget::title {{ background: {bar}; padding: 6px 10px; border-top: 1px solid {border}; }}
QComboBox QAbstractItemView {{ background: {field}; color: {text}; border: 1px solid {field_border}; selection-background-color: {hover}; selection-color: {text_strong}; }}
QPushButton {{ background: {button}; color: {text}; border: 1px solid {button_border}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {pressed}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 18px; color: {muted}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {text_strong}; border-bottom: 2px solid {accent}; }}
QTabWidget#pages > QTabBar {{ background: {bar}; }}
QTabWidget#pages > QTabBar::tab {{ padding: 9px 22px; font-weight: 600; background: {bar}; border-bottom: 2px solid {bar}; }}
QTabWidget#pages > QTabBar::tab:selected {{ color: {text_strong}; background: {bg}; border-bottom: 2px solid {accent}; }}
QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 10px; }}
QFrame#sep {{ background: {border}; }}
QLabel#cardTitle {{ color: {hint}; font-size: 8pt; letter-spacing: 1px; }}
QLabel#cardValue {{ font-size: 17pt; font-weight: 600; color: {text_strong}; }}
QLabel#cardValue[state="good"] {{ color: {good}; }}
QLabel#cardValue[state="warn"] {{ color: {warn}; }}
QLabel#cardValue[state="bad"] {{ color: {bad}; }}
QLabel#cardSub {{ color: {hint}; font-size: 8.5pt; }}
QSplitter::handle {{ background: {border}; }}
QStatusBar {{ background: {bar}; color: {muted}; border-top: 1px solid {border}; }}
QScrollArea {{ background: {bg}; }}
"""


def _arrow_icon(color: str, up: bool) -> str:
    """Draw a small triangle PNG in the given colour (no image plugins needed); return its path."""
    import os
    import tempfile
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPolygonF
    folder = os.path.join(tempfile.gettempdir(), "coilspring_icons")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"arrow_{'up' if up else 'down'}_{color.lstrip('#')}.png")
    if not os.path.exists(path):
        scale = 4                                   # draw large so it stays crisp when scaled
        img = QImage(8 * scale, 5 * scale, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        w, h = 8 * scale, 5 * scale
        pts = ([QPointF(0, h), QPointF(w, h), QPointF(w / 2, 0)] if up else
               [QPointF(0, 0), QPointF(w, 0), QPointF(w / 2, h)])
        p.drawPolygon(QPolygonF(pts))
        p.end()
        img.save(path, "PNG")
    return path.replace("\\", "/")


def _mark_icon(color: str, kind: str) -> str:
    """Tick ('check') or radio dot ('dot') PNG in the given colour; returns its path."""
    import os
    import tempfile
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen
    folder = os.path.join(tempfile.gettempdir(), "coilspring_icons")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{kind}_{color.lstrip('#')}.png")
    if not os.path.exists(path):
        n = 56                                      # drawn large, shown at 14 px
        img = QImage(n, n, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        if kind == "check":
            pen = QPen(QColor(color), n * 0.14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            tick = QPainterPath(QPointF(n * 0.22, n * 0.52))
            tick.lineTo(n * 0.42, n * 0.72)
            tick.lineTo(n * 0.78, n * 0.30)
            p.drawPath(tick)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(n * 0.25, n * 0.25, n * 0.5, n * 0.5))
        p.end()
        img.save(path, "PNG")
    return path.replace("\\", "/")


def stylesheet() -> str:
    vals = {k: v for k, v in T.items() if isinstance(v, str)}
    vals["icon_up"] = _arrow_icon(T["muted"], True)
    vals["icon_down"] = _arrow_icon(T["muted"], False)
    vals["icon_check"] = _mark_icon(T["accent_text"], "check")
    vals["icon_dot"] = _mark_icon(T["accent"], "dot")
    return _STYLE.format(**vals)


def style_plot(plot):
    """Apply theme colours to a pyqtgraph PlotWidget's background and axes."""
    import pyqtgraph as pg
    plot.setBackground(c("plot_bg"))
    for name in ("left", "bottom"):
        ax = plot.getAxis(name)
        ax.setPen(pg.mkPen(c("axis")))
        ax.setTextPen(pg.mkPen(c("axis")))
    plot.showGrid(x=True, y=True, alpha=0.15 if is_dark() else 0.25)
