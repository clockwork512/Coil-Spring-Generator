"""Developer mode: ƒ buttons beside values and a bottom inspector panel (like F12).

Turn it on with the Developer button in the toolbar (or F12). Click any ƒ to see how
that value is calculated: formula, the numbers that went into it, what it depends on,
what uses it, and the line of source code that computes it.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QTabWidget, QTextBrowser, QPlainTextEdit, QPushButton, QLabel, QToolButton,
)

from . import theme
from .trace import Trace, f

# every ƒ button in the window, so they can be shown / hidden together
_BUTTONS: list["DevButton"] = []
_handler = None
_visible = False


def set_handler(fn):
    global _handler
    _handler = fn


def set_buttons_visible(on: bool):
    global _visible
    _visible = on
    for b in _BUTTONS:
        b.setVisible(on and b.key is not None)


class DevButton(QToolButton):
    def __init__(self, key=None, parent=None):
        super().__init__(parent)
        self.setObjectName("devbtn")
        self.setText("ƒ")
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        self.key = None
        self.set_key(key)
        self.clicked.connect(lambda: _handler and self.key and _handler(self.key))
        _BUTTONS.append(self)

    def set_key(self, key, label=None):
        self.key = key
        self.setToolTip(f"Show how {label or 'this value'} is calculated")
        self.setVisible(_visible and key is not None)


def with_dev(widget, key, label=None):
    """Wrap a value label so a ƒ button sits to its right."""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(widget, 1)
    btn = DevButton(None, box)
    lay.addWidget(btn)
    btn.set_key(key, label)
    box.dev = btn
    return box


# ---------------------------------------------------------------------------
def shown_value(u, v):
    """The value as the app displays it in the current units (or '' if the same)."""
    if not isinstance(v.value, (int, float)):
        return ""
    x = float(v.value)
    k = v.kind
    if k == "len":
        return u.fl(x)
    if k == "force":
        return u.ff(x)
    if k == "rate":
        return u.fr(x)
    if k in ("stress", "mod"):
        return u.fs(x)
    if k == "press":
        return f"{x / 0.006894757:.2f} psi"
    if k == "mass" and u.imperial:
        return f"{u.mass(x):.3f} oz"
    return ""


def _val(v):
    if isinstance(v.value, str):
        return v.value
    return f"{f(v.value)} {v.unit}".strip()


class Inspector(QDockWidget):
    def __init__(self, main):
        super().__init__("Developer – calculation inspector", main)
        self.main = main
        self.setObjectName("inspector")
        self.trace: Trace | None = None
        self.current = "k"

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)
        note = QLabel("All math runs in mm, N and MPa – the same numbers the app shows, before unit "
                      "conversion. Click a ƒ next to any value, or pick a variable below.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        root.addWidget(note)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter variables…")
        self.filter.textChanged.connect(self._apply_filter)
        lv.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Variable", "Value"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setColumnWidth(0, 250)
        self.tree.currentItemChanged.connect(self._on_item)
        lv.addWidget(self.tree, 1)
        split.addWidget(left)

        self.tabs = QTabWidget()
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.detail.anchorClicked.connect(self._on_link)
        self.tabs.addTab(self.detail, "Variable")
        logw = QWidget()
        ll = QVBoxLayout(logw)
        ll.setContentsMargins(0, 4, 0, 0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSizeF(9.5)
        self.log.setFont(mono)
        ll.addWidget(self.log, 1)
        copy = QPushButton("Copy log")
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(self.log.toPlainText()),
                                      self.main.statusBar().showMessage("Calculation log copied", 3000)))
        ll.addWidget(copy, 0, Qt.AlignRight)
        self.tabs.addTab(logw, "Calculation log")
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 1)
        split.setSizes([380, 900])
        root.addWidget(split, 1)
        self.setWidget(body)
        self.setMinimumHeight(240)

    # ------------------------------------------------------------------
    def refresh(self, t: Trace):
        self.trace = t
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}
        select = None
        for v in t:
            g = groups.get(v.group)
            if g is None:
                g = QTreeWidgetItem([v.group or "Other", ""])
                g.setFlags(g.flags() & ~Qt.ItemIsSelectable)
                fnt = g.font(0)
                fnt.setBold(True)
                g.setFont(0, fnt)
                self.tree.addTopLevelItem(g)
                g.setExpanded(True)
                groups[v.group] = g
            mark = "  ≠" if v.matches is False else ""
            it = QTreeWidgetItem([f"{v.symbol}   {v.name}", _val(v) + mark])
            it.setData(0, Qt.UserRole, v.key)
            if v.matches is False:
                it.setForeground(1, theme.c("bad"))
            g.addChild(it)
            if v.key == self.current:
                select = it
        self.tree.blockSignals(False)
        self._apply_filter(self.filter.text())
        if select is not None:
            self.tree.setCurrentItem(select)
        self._render(self.current)
        self._render_log()

    def show_var(self, key):
        self.current = key
        self.tabs.setCurrentIndex(0)
        it = self._find(key)
        if it is not None:
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)
        self._render(key)

    def _find(self, key):
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                if g.child(j).data(0, Qt.UserRole) == key:
                    return g.child(j)
        return None

    def _apply_filter(self, text):
        text = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            any_shown = False
            for j in range(g.childCount()):
                c = g.child(j)
                show = not text or text in c.text(0).lower() or text in str(c.data(0, Qt.UserRole)).lower()
                c.setHidden(not show)
                any_shown |= show
            g.setHidden(not any_shown)

    def _on_item(self, cur, _prev):
        if cur is not None and cur.data(0, Qt.UserRole):
            self.current = cur.data(0, Qt.UserRole)
            self._render(self.current)

    def _on_link(self, url: QUrl):
        if url.scheme() == "var":
            self.show_var(url.path() or url.host())

    # ------------------------------------------------------------------
    def _link(self, key):
        v = self.trace.get(key) if self.trace else None
        if v is None:
            return html.escape(key)
        return (f"<a href='var:{key}' style='color:{theme.T['accent']};text-decoration:none'>"
                f"<b>{html.escape(v.symbol)}</b></a> <span style='color:{theme.T['hint']}'>"
                f"{html.escape(v.name)} = {html.escape(_val(v))}</span>")

    def _render(self, key):
        T = theme.T
        v = self.trace.get(key) if self.trace else None
        if v is None:
            self.detail.setHtml(f"<p style='color:{T['hint']}'>No value to show – the spring isn't valid "
                                "right now, or this page isn't in use.</p>")
            return
        e = html.escape
        code = (f"background:{T['code_bg']};color:{T['code_text']};padding:8px 10px;"
                f"border:1px solid {T['border']};font-family:Consolas,'Cascadia Mono',monospace;")
        out = [f"<h2 style='margin:0 0 2px 0;color:{T['text_strong']}'>{e(v.symbol)} "
               f"<span style='font-weight:normal;color:{T['muted']}'>– {e(v.name)}</span></h2>",
               f"<p style='color:{T['hint']};margin-top:0'>{e(v.group)}  ·  key <code>{e(v.key)}</code></p>"]
        out.append(f"<table cellspacing='0' cellpadding='3'>")
        out.append(f"<tr><td style='color:{T['hint']}'>Formula</td><td style='font-size:12pt'>"
                   f"<b>{e(v.formula)}</b></td></tr>")
        if v.subst:
            out.append(f"<tr><td style='color:{T['hint']}'>With values</td><td>= {e(v.subst)}</td></tr>")
        shown = shown_value(self.main.u, v)
        res = f"= <b style='color:{T['accent']};font-size:12pt'>{e(_val(v))}</b>"
        if shown and shown.replace(" ", "") != _val(v).replace(" ", ""):
            res += f"  <span style='color:{T['hint']}'>(shown as {e(shown)})</span>"
        out.append(f"<tr><td style='color:{T['hint']}'>Result</td><td>{res}</td></tr>")
        if v.matches is True:
            out.append(f"<tr><td></td><td style='color:{T['good']}'>✓ Matches the value the app uses "
                       f"(<code>{e(v.check_label)}</code>)</td></tr>")
        elif v.matches is False:
            out.append(f"<tr><td></td><td style='color:{T['bad']}'>≠ The app uses {e(f(v.check))} "
                       f"(<code>{e(v.check_label)}</code>). The code in calc.py has changed – update the "
                       f"formula text in trace.py to match.</td></tr>")
        out.append("</table>")
        if v.note:
            out.append(f"<p style='color:{T['muted']}'>{e(v.note)}</p>")
        if v.deps:
            out.append(f"<p style='margin-bottom:2px;color:{T['hint']}'>DEPENDS ON</p><p style='margin-top:0'>"
                       + "<br>".join(self._link(d) for d in v.deps) + "</p>")
        if v.used_by:
            out.append(f"<p style='margin-bottom:2px;color:{T['hint']}'>USED BY</p><p style='margin-top:0'>"
                       + "<br>".join(self._link(d) for d in v.used_by) + "</p>")
        if v.sources:
            out.append(f"<p style='margin-bottom:2px;color:{T['hint']}'>SOURCE CODE</p>")
            for fn, ln, src in v.sources:
                where = f"{fn}, line {ln}" if ln else fn
                out.append(f"<p style='margin:6px 0 2px 0;color:{T['muted']}'>{e(where)}</p>"
                           f"<pre style='{code}'>{e(src)}</pre>")
        self.detail.setHtml("".join(out))

    def _render_log(self):
        if not self.trace:
            self.log.setPlainText("")
            return
        lines = ["# Coil Spring Designer – calculation log (internal units: mm, N, MPa)", ""]
        group = None
        for v in self.trace:
            if v.group != group:
                group = v.group
                lines += ["", f"## {group}"]
            check = {True: "  ✓", False: f"  ≠ app uses {f(v.check)}", None: ""}[v.matches]
            loc = ", ".join(f"{fn}:{ln}" for fn, ln, _ in v.sources if ln)
            if v.formula in ("input", "material table") or not v.subst:
                lines.append(f"{v.symbol:<12} = {_val(v):<22} {v.formula}" + (f"   [{loc}]" if loc else "") + check)
            else:
                lines.append(f"{v.symbol:<12} = {v.formula}")
                lines.append(f"{'':<12} = {v.subst}")
                lines.append(f"{'':<12} = {_val(v)}" + (f"   [{loc}]" if loc else "") + check)
        self.log.setPlainText("\n".join(lines))
