"""Calendar screen with month, week, and day views."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from ...core import dates as D
from .dialogs import CategoryDialog, EventDialog, ReadOnlyEventDialog, ask_scope
from .models import Occurrence
from .subscriptions import Subscription, normalize_url

HOUR_H, GUTTER, CHIP_H = 52, 58, 18
INK, MUTED, FAINT, LINE, SURFACE, DIM, ACCENT, TODAY_BG, NOW = (
    "#252a32", "#747c88", "#a3a9b2", "#d9dde2", "#ffffff", "#f4f5f7",
    "#3977d5", "#edf4ff", "#d64a45",
)


def _color(value: str) -> QColor:
    return QColor(value)


def _tint(value: str, amount: float) -> QColor:
    c = _color(value)
    return QColor(int(c.red() * amount + 255 * (1 - amount)),
                  int(c.green() * amount + 255 * (1 - amount)),
                  int(c.blue() * amount + 255 * (1 - amount)))


def _shade(value: str, amount: float) -> QColor:
    c = _color(value)
    return QColor(int(c.red() * amount), int(c.green() * amount), int(c.blue() * amount))


def _on_color(value: str) -> QColor:
    c = _color(value)
    return QColor("#ffffff" if (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000 < 145 else "#20242a")


class _CalendarCanvas(QWidget):
    def __init__(self, view: "CalendarView", head: bool = False):
        super().__init__(view)
        self.view, self.head = view, head
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(250, 80)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), _color(SURFACE))
        if self.head:
            self.view._draw_header(p, self.width(), self.height())
        elif self.view.mode == "month":
            self.view._draw_month(p, self.width(), self.height())
        else:
            self.view._draw_timed(p, self.width())
        self.view._draw_ghost(p, self)
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.view._press(self, event.position())

    def mouseMoveEvent(self, event) -> None:
        self.view._motion(self, event.position())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.view._release(self, event.position())

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.view._double(self, event.position())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Left:
            self.view.step(-1)
        elif event.key() == Qt.Key.Key_Right:
            self.view.step(1)
        elif event.key() == Qt.Key.Key_T:
            self.view.go_today()
        else:
            super().keyPressEvent(event)


class CalendarView(QWidget):
    def __init__(self, parent: QWidget, cal):
        super().__init__(parent)
        self.cal = cal
        self.mode = "month"
        self.cursor = date.today()
        self.first_weekday = D.SUNDAY
        self.hidden: set = set()
        self._hits: list = []
        self._head_hits: list = []
        self._col_days: list[date] = []
        self._colw = 1.0
        self._scroll_frac = 6.5 / 24
        self._press_info = None
        self._dragging = False
        self._pending_edit = QTimer(self)
        self._pending_edit.setSingleShot(True)
        self._pending_edit.timeout.connect(self._finish_pending_edit)
        self._pending_occ = None
        self._subs = [("calendar.*", self._on_change), ("vault.reloaded", self._on_change)]
        for pattern, handler in self._subs:
            cal.api.on(pattern, handler)
        self.destroyed.connect(self._cleanup)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.redraw)
        self._timer.start(60_000)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        bar = QHBoxLayout()
        root.addLayout(bar)
        self._button(bar, "‹", lambda: self.step(-1))
        self._button(bar, "Today", self.go_today)
        self._button(bar, "›", lambda: self.step(1))
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        bar.addWidget(self.title_label)
        bar.addStretch(1)
        for label in ("Month", "Week", "Day"):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(label.lower() == self.mode)
            b.clicked.connect(lambda checked=False, m=label.lower(): self.set_mode(m))
            bar.addWidget(b)
            setattr(self, f"{label.lower()}_button", b)
        self._button(bar, "New event", self.new_event)
        more = QToolButton()
        more.setText("More")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(more)
        more.setMenu(self.more_menu)
        self.more_menu.addAction("Import .ics file…", self.import_ics)
        self.more_menu.addAction("Export .ics file…", self.export_ics)
        self.more_menu.addAction("Calendar links (.ics)…", self.open_subscriptions)
        self.more_menu.addSeparator()
        self.filter_menu = self.more_menu.addMenu("Show categories")
        self.more_menu.addAction("Manage categories…", self.manage_categories)
        bar.addWidget(more)

        self.head = _CalendarCanvas(self, head=True)
        self.head.setFixedHeight(0)
        root.addWidget(self.head)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = _CalendarCanvas(self)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().valueChanged.connect(self._remember_scroll)
        self._rebuild_filter_menu()
        self._resize_canvas()

    def _cleanup(self, *_args) -> None:
        for pattern, handler in self._subs:
            self.cal.api.off(pattern, handler)

    @staticmethod
    def _button(layout, text, callback) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_canvas()

    def _resize_canvas(self) -> None:
        w = max(250, self.scroll.viewport().width())
        if self.mode == "month":
            self.body.setFixedSize(w, max(450, self.scroll.viewport().height()))
        else:
            self.body.setFixedSize(w, 24 * HOUR_H)
            self.head.setFixedSize(w, self.head.height())
        self.redraw()

    def _rebuild_filter_menu(self) -> None:
        self.filter_menu.clear()
        self._filter_actions = {}
        for key, label in [(c.id, c.name) for c in self.cal.categories()] + [(None, "No category")]:
            action = QAction(label, self.filter_menu)
            action.setCheckable(True)
            action.setChecked(key not in self.hidden)
            action.toggled.connect(lambda checked, k=key: self._toggle(k, checked))
            self.filter_menu.addAction(action)
            self._filter_actions[key] = action

    def _toggle(self, key, shown: bool) -> None:
        (self.hidden.discard if shown else self.hidden.add)(key)
        self.redraw()

    def step(self, n: int) -> None:
        if self.mode == "month":
            self.cursor = D.add_months(self.cursor.replace(day=1), n)
        else:
            self.cursor += timedelta(days=(7 if self.mode == "week" else 1) * n)
        self.redraw()

    def go_today(self) -> None:
        self.cursor = date.today()
        self.redraw()

    def set_mode(self, mode: str) -> None:
        today = date.today()
        if mode != "month" and self.mode == "month" and (self.cursor.year, self.cursor.month) == (today.year, today.month):
            self.cursor = today
        if self.mode != "month":
            self._remember_scroll()
        self.mode = mode
        for name in ("month", "week", "day"):
            getattr(self, f"{name}_button").setChecked(name == mode)
        self.head.setFixedHeight(0 if mode == "month" else 50)
        self._resize_canvas()
        self.redraw()

    def _range(self) -> tuple[date, date]:
        if self.mode == "month":
            grid = D.month_grid(self.cursor.year, self.cursor.month, self.first_weekday)
            return grid[0][0], grid[-1][-1] + timedelta(days=1)
        if self.mode == "week":
            start = D.week_start(self.cursor, self.first_weekday)
            return start, start + timedelta(days=7)
        return self.cursor, self.cursor + timedelta(days=1)

    def _title(self) -> str:
        if self.mode == "month":
            return f"{self.cursor:%B %Y}"
        first, last = self._range()
        end = last - timedelta(days=1)
        if self.mode == "day":
            return D.fmt_date_long(first)
        if first.month == end.month:
            return f"{first:%b} {first.day} – {end.day}, {end.year}"
        return f"{first:%b} {first.day} – {end:%b} {end.day}, {end.year}"

    def _on_change(self, topic: str = "", **_) -> None:
        if topic in ("calendar.categories.changed", "vault.reloaded"):
            self._rebuild_filter_menu()
        QTimer.singleShot(0, self.redraw)

    def _remember_scroll(self, *_args) -> None:
        if self.mode != "month":
            bar = self.scroll.verticalScrollBar()
            self._scroll_frac = bar.value() / max(1, bar.maximum() + bar.pageStep())

    def redraw(self) -> None:
        self.title_label.setText(self._title())
        first, last = self._range()
        self._occurrences = self.cal.occurrences_between(D.day_start(first), D.day_start(last), self.hidden)
        self.body.update()
        if self.mode != "month":
            self.head.update()
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
                round(self._scroll_frac * self.scroll.verticalScrollBar().maximum())))

    @staticmethod
    def _fit(p: QPainter, text: str, max_width: float) -> str:
        text = text.replace("\n", " ")
        if p.fontMetrics().horizontalAdvance(text) <= max_width:
            return text
        while text and p.fontMetrics().horizontalAdvance(text + "…") > max_width:
            text = text[:-1]
        return text.rstrip() + "…" if text else ""

    @staticmethod
    def _bucket(occs: list[Occurrence]) -> dict[date, list[Occurrence]]:
        result: dict[date, list[Occurrence]] = defaultdict(list)
        for occ in occs:
            for day in occ.days():
                result[day].append(occ)
        for items in result.values():
            items.sort(key=lambda o: (not o.all_day, o.start, o.title.lower()))
        return result

    @staticmethod
    def _layout(items: list[tuple]) -> list[tuple]:
        result, cluster, col_ends, cluster_end = [], [], [], None
        def flush():
            result.extend((s, e, o, col, len(col_ends)) for s, e, o, col in cluster)
        for s, e, o in sorted(items, key=lambda x: (x[0], x[1])):
            if cluster and s >= cluster_end:
                flush()
                cluster, col_ends, cluster_end = [], [], None
            for col, end in enumerate(col_ends):
                if s >= end:
                    col_ends[col] = e
                    break
            else:
                col = len(col_ends)
                col_ends.append(e)
            cluster.append((s, e, o, col))
            cluster_end = e if cluster_end is None else max(cluster_end, e)
        if cluster:
            flush()
        return result

    def _text(self, p, x, y, text, color=INK, size=9, bold=False,
              align=Qt.AlignmentFlag.AlignLeft, width=1000):
        font = QFont()
        font.setPointSize(size)
        font.setBold(bold)
        p.setFont(font)
        p.setPen(_color(color))
        p.drawText(QRectF(x, y - size - 2, width, size + 8), align, text)

    def _draw_month(self, p: QPainter, w: int, h: int) -> None:
        grid = D.month_grid(self.cursor.year, self.cursor.month, self.first_weekday)
        hdr, cw = 32, w / 7
        ch = (h - hdr) / 6
        today, by_day = date.today(), self._bucket(self._occurrences)
        self._hits = []
        for i, d in enumerate(grid[0]):
            self._text(p, i * cw + 10, hdr / 2 + 5, f"{d:%a}", MUTED)
        for r, week in enumerate(grid):
            for i, d in enumerate(week):
                x0, y0, x1, y1 = i * cw, hdr + r * ch, (i + 1) * cw, hdr + (r + 1) * ch
                in_month = d.month == self.cursor.month
                p.fillRect(QRectF(x0, y0, cw, ch), _color(TODAY_BG if d == today else (SURFACE if in_month else DIM)))
                p.setPen(_color(LINE))
                p.drawRect(QRectF(x0, y0, cw, ch))
                self._hits.append((QRectF(x0, y0, cw, ch), "day", d))
                if d == today:
                    p.setBrush(_color(ACCENT))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(QRectF(x0 + 6, y0 + 5, 22, 22))
                    self._text(p, x0 + 6, y0 + 17, str(d.day), "#ffffff", 10, True,
                               Qt.AlignmentFlag.AlignHCenter, 22)
                else:
                    label = f"{d:%b} {d.day}" if d.day == 1 else str(d.day)
                    self._text(p, x0 + 10, y0 + 18, label, INK if in_month else FAINT, 10, True)
                items = by_day.get(d, [])
                cap = max(0, int((ch - 34) // (CHIP_H + 2)))
                shown = items if len(items) <= cap else items[:max(cap - 1, 0)]
                y = y0 + 32
                for occ in shown:
                    self._month_chip(p, occ, x0 + 4, y, x1 - 4)
                    y += CHIP_H + 2
                if len(items) > len(shown) and y + CHIP_H <= y1 + 2:
                    self._text(p, x0 + 10, y + CHIP_H / 2 + 5, f"+{len(items)-len(shown)}", MUTED)
                    self._hits.append((QRectF(x0 + 4, y, x1 - x0 - 8, CHIP_H), "more", d))

    def _month_chip(self, p: QPainter, occ: Occurrence, x0: float, y: float, x1: float) -> None:
        col = self.cal.color_of(occ.event)
        if occ.all_day or len(occ.days()) > 1:
            p.fillRect(QRectF(x0, y, x1 - x0, CHIP_H), _color(col))
            text, color = occ.title, _on_color(col)
        else:
            p.setBrush(_color(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x0 + 4, y + 6, 6, 6))
            text, color = f"{D.fmt_time_short(occ.start)} {occ.title}", _color(INK)
        self._text(p, x0 + 15 if not (occ.all_day or len(occ.days()) > 1) else x0 + 6,
                   y + CHIP_H / 2 + 4, self._fit(p, text, x1 - x0 - 18), color.name(), 9)
        self._hits.append((QRectF(x0, y, x1 - x0, CHIP_H), "event", occ))

    def _draw_header(self, p: QPainter, w: int, h: int) -> None:
        first, last = self._range()
        days = [first + timedelta(days=i) for i in range((last-first).days)]
        colw = (w-GUTTER) / len(days)
        rows, placed = [], []
        allday = sorted((o for o in self._occurrences if o.all_day),
                        key=lambda o: (o.start, -(o.end-o.start).total_seconds()))
        for occ in allday:
            c0 = max((occ.days()[0]-first).days, 0)
            c1 = min((occ.days()[-1]-first).days, len(days)-1)
            for row, used in enumerate(rows):
                if all(c1 < a or c0 > b for a,b in used):
                    used.append((c0,c1)); placed.append((occ,c0,c1,row)); break
            else:
                rows.append([(c0,c1)]); placed.append((occ,c0,c1,len(rows)-1))
        shown = min(len(rows), 4)
        height = 50 + shown*(CHIP_H+3) + (6 if shown else 0)
        if self.head.height() != height:
            self.head.setFixedHeight(height)
        today = date.today()
        self._head_hits = []
        for i,d in enumerate(days):
            x = GUTTER + i*colw
            if d == today:
                p.fillRect(QRectF(x,0,colw,height),_color(TODAY_BG))
            p.setPen(_color(LINE)); p.drawLine(QPointF(x,0),QPointF(x,height))
            self._text(p,x+10,17,f"{d:%a}",ACCENT if d==today else MUTED)
            self._text(p,x+10,39,str(d.day),ACCENT if d==today else INK,15,True)
            self._head_hits.append((QRectF(x,0,colw,height),"allday",d))
        p.setPen(_color(LINE)); p.drawLine(0,height-1,w,height-1)
        if shown:
            self._text(p,0,50+CHIP_H/2+5,"all day",MUTED,8,False,Qt.AlignmentFlag.AlignRight,GUTTER-8)
        for occ,c0,c1,row in placed:
            if row >= shown: continue
            x0,x1=GUTTER+c0*colw+3,GUTTER+(c1+1)*colw-3
            y=50+row*(CHIP_H+3); color=self.cal.color_of(occ.event)
            p.fillRect(QRectF(x0,y,x1-x0,CHIP_H),_color(color))
            self._text(p,x0+6,y+CHIP_H/2+4,self._fit(p,occ.title,x1-x0-12),_on_color(color).name())
            self._head_hits.append((QRectF(x0,y,x1-x0,CHIP_H),"event",occ))
        extra=sum(1 for _,_,_,r in placed if r>=shown)
        if extra:         self._text(p,0,height-5,f"+{extra}",MUTED,9,False,Qt.AlignmentFlag.AlignRight,GUTTER-8)

    def _draw_timed(self, p: QPainter, w: int) -> None:
        first,last=self._range()
        days=[first+timedelta(days=i) for i in range((last-first).days)]
        n=len(days); colw=(w-GUTTER)/n; self._colw,self._col_days=colw,days
        today=date.today(); total=24*HOUR_H
        for i,d in enumerate(days):
            if d==today: p.fillRect(QRectF(GUTTER+i*colw,0,colw,total),_color(TODAY_BG))
        for hr in range(24):
            y=hr*HOUR_H
            p.setPen(_color(LINE)); p.drawLine(QPointF(GUTTER,y),QPointF(w,y))
            p.setPen(_color("#eceef0")); p.drawLine(QPointF(GUTTER,y+HOUR_H/2),QPointF(w,y+HOUR_H/2))
            if hr: self._text(p,0,y+4,D.fmt_hour(hr),MUTED,8,False,Qt.AlignmentFlag.AlignRight,GUTTER-8)
        for i in range(n+1):
            x=GUTTER+i*colw
            p.setPen(_color(LINE)); p.drawLine(QPointF(x,0),QPointF(x,total))
        self._hits=[]
        for i,d in enumerate(days):
            x0=GUTTER+i*colw
            self._hits.append((QRectF(x0,0,colw,total),"slot",d))
            day0=D.day_start(d); day1=day0+timedelta(days=1); items=[]
            for occ in self._occurrences:
                if occ.all_day: continue
                effective=max(occ.end,occ.start+timedelta(minutes=30))
                if occ.start<day1 and effective>day0:
                    items.append((max(occ.start,day0),min(effective,day1),occ))
            for s,e,occ,col,count in self._layout(items):
                width=(colw-6)/count; bx0=x0+3+col*width; bx1=bx0+width-2
                y0=(s-day0).total_seconds()/3600*HOUR_H+1
                y1=(e-day0).total_seconds()/3600*HOUR_H-1
                color=self.cal.color_of(occ.event)
                p.fillRect(QRectF(bx0,y0,bx1-bx0,y1-y0),_tint(color,.8))
                p.fillRect(QRectF(bx0,y0,4,y1-y0),_color(color))
                self._text(p,bx0+9,y0+14,self._fit(p,occ.title,bx1-bx0-12),_shade(color,.55).name(),9,True)
                if y1-y0>=38:
                    sub=f"{D.fmt_time(occ.start)} – {D.fmt_time(occ.end)}"
                    if occ.event.location: sub+=f"  ·  {occ.event.location}"
                    self._text(p,bx0+9,y0+29,self._fit(p,sub,bx1-bx0-12),_shade(color,.4).name(),9)
                self._hits.append((QRectF(bx0,y0,bx1-bx0,y1-y0),"event",occ))
        if today in days:
            x=GUTTER+days.index(today)*colw
            y=(datetime.now()-D.day_start(today)).total_seconds()/3600*HOUR_H
            p.setPen(QPen(_color(NOW),2)); p.drawLine(QPointF(x,y),QPointF(x+colw,y))
            p.setBrush(_color(NOW)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(x,y),4,4)

    def _find(self, canvas, pos):
        y = pos.y() + (self.scroll.verticalScrollBar().value() if canvas is self.body and self.mode != "month" else 0)
        x = pos.x()
        hits = self._head_hits if canvas is self.head else self._hits
        for rect, kind, payload in reversed(hits):
            if rect.contains(x,y):
                return kind,payload,y
        return None,None,y

    @staticmethod
    def _snap(minutes: float) -> int:
        return round(minutes/15)*15

    def _day_at(self, x, y):
        for rect,kind,payload in self._hits:
            if kind=="day" and rect.contains(x,y): return payload
        return None

    def _press(self, canvas, pos) -> None:
        self._pending_edit.stop()
        kind,payload,y=self._find(canvas,pos)
        info={"canvas":canvas,"kind":kind,"payload":payload,"x":pos.x(),"y":pos.y()}
        if kind=="event" and canvas is self.body and not payload.all_day and self.mode!="month":
            col=self._column_at(pos.x())
            if col is not None:
                day0=D.day_start(self._col_days[col])
                info["grab"]=y/HOUR_H*60-(max(payload.start,day0)-day0).total_seconds()/60
        self._press_info=info; self._dragging=False

    def _motion(self, canvas, pos) -> None:
        info=self._press_info
        if info and info["kind"]=="event":
            info["current"]=(canvas,pos)
            self._dragging |= abs(pos.x()-info["x"])+abs(pos.y()-info["y"])>=5
            if self._dragging: self.body.update(); self.head.update()

    def _draw_ghost(self, painter, canvas):
        info = self._press_info
        if not self._dragging or not info or "current" not in info:
            return
        target_canvas, pos = info["current"]
        if target_canvas is not canvas:
            return
        target = self._target(target_canvas, pos)
        if not target:
            return
        occ, new_start = target
        pen = QPen(_color(ACCENT), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.mode == "month":
            day = new_start.date()
            for rect, kind, payload in self._hits:
                if kind == "day" and payload == day:
                    painter.drawRect(rect.adjusted(2, 2, -2, -2))
                    break
        elif canvas is self.body and new_start.date() in self._col_days:
            col = self._col_days.index(new_start.date())
            top = (new_start - D.day_start(new_start.date())).total_seconds() / 3600 * HOUR_H
            height = max((occ.end - occ.start).total_seconds() / 3600 * HOUR_H, 18)
            x = GUTTER + col * self._colw + 3
            painter.drawRect(QRectF(x, top, self._colw - 6, height))
        elif canvas is self.head and self._col_days:
            col = (new_start.date() - self._col_days[0]).days
            if 0 <= col < len(self._col_days):
                x = GUTTER + col * self._colw + 3
                y = 52
                painter.drawRect(QRectF(x, y, self._colw - 6, CHIP_H))

    def _release(self, canvas, pos) -> None:
        info=self._press_info
        if not info: return
        if self._dragging:
            target=self._target(canvas,pos)
            self._press_info=None; self._dragging=False
            if target: self._apply_move(*target)
            return
        self._press_info=None
        if info["kind"]=="event":
            self._pending_occ=info["payload"]; self._pending_edit.start(250)
        elif info["kind"]=="more":
            self.cursor=info["payload"]; self.set_mode("day")

    def _finish_pending_edit(self) -> None:
        if self._pending_occ: self.edit(self._pending_occ)
        self._pending_occ=None

    def _column_at(self,x):
        if not self._col_days or x<GUTTER:return None
        i=int((x-GUTTER)//self._colw)
        return i if 0<=i<len(self._col_days) else None

    def _target(self,canvas,pos):
        info=self._press_info
        if not info or info["kind"]!="event":return None
        occ=info["payload"]; kind,payload,y=self._find(canvas,pos)
        if self.mode=="month":
            day=self._day_at(pos.x(),y)
            return None if day is None else (occ,occ.start+timedelta(days=(day-occ.start.date()).days))
        col=self._column_at(pos.x())
        if col is None:return None
        day=self._col_days[col]
        if occ.all_day or canvas is self.head:
            return occ,occ.start+timedelta(days=(day-occ.start.date()).days)
        length=(occ.end-occ.start).total_seconds()/60
        minutes=self._snap(y/HOUR_H*60-info.get("grab",0))
        minutes=max(0,min(minutes,max(0,24*60-int(length))))
        return occ,D.day_start(day)+timedelta(minutes=minutes)

    def _double(self,canvas,pos):
        self._pending_edit.stop(); self._pending_occ=None
        kind,payload,y=self._find(canvas,pos)
        if kind=="day": self.new_event(datetime.combine(payload,time(9)))
        elif kind=="slot":
            minutes=int(y/HOUR_H*60)//30*30
            self.new_event(D.day_start(payload)+timedelta(minutes=min(minutes,23*60)))
        elif kind=="allday": self.new_event(D.day_start(payload),all_day=True)

    def _apply_move(self,occ,new_start):
        if new_start==occ.start:return
        ev=self.cal.get_event(occ.event.id)
        if ev is None:return
        if ev.source:
            QMessageBox.information(self,"Read-only","This event comes from a calendar link, so it can't be moved here. Click it to read its details.")
            return
        scope="this"
        if ev.rrule:
            scope=ask_scope(self,"Move")
            if scope is None:return
        self.cal.move_occurrence(ev.id,occ.start,new_start,scope)

    def new_event(self,start:datetime|None=None,all_day:bool=False):
        if start is None:
            first,last=self._range(); today=date.today()
            day=today if first<=today<last else self.cursor
            if day==today:
                start=D.now().replace(minute=0,second=0)+timedelta(hours=1)
                if start.date()!=today:start=datetime.combine(today,time(23))
            else:start=datetime.combine(day,time(9))
        EventDialog(self,self.cal,start=start,end=start+(timedelta(days=1) if all_day else timedelta(hours=1)),all_day=all_day)

    def edit(self,occ):
        event=self.cal.get_event(occ.event.id)
        if event and event.source:ReadOnlyEventDialog(self,self.cal,event,occ)
        elif event:EventDialog(self,self.cal,event=event,occurrence=occ)

    def open_subscriptions(self): SubscriptionsWindow(self,self.cal)
    def manage_categories(self): CategoryDialog(self,self.cal)

    def import_ics(self):
        path,_=QFileDialog.getOpenFileName(self,"Import calendar file","","iCalendar (*.ics);;All files (*)")
        if not path:return
        try:result=self.cal.import_ics(Path(path).read_text(encoding="utf-8-sig",errors="replace"))
        except Exception as exc:
            logging.getLogger(__name__).exception("Calendar import failed")
            QMessageBox.critical(self,"Import failed",f"That file couldn't be imported.\n\n{exc}")
        else:QMessageBox.information(self,"Import finished",result.summary())

    def export_ics(self):
        path,_=QFileDialog.getSaveFileName(self,"Export calendar","cerealbox-calendar.ics","iCalendar (*.ics)")
        if path:
            if not Path(path).suffix:path += ".ics"
            Path(path).write_bytes(self.cal.export_ics().encode("utf-8"))
            QMessageBox.information(self,"Export finished",f"Saved to {path}")


class SubscriptionDialog(QDialog):
    def __init__(self,parent:QWidget,cal):
        super().__init__(parent); self.cal=cal; self.setWindowTitle("Add calendar link")
        root=QVBoxLayout(self)
        root.addWidget(QLabel("Paste the .ics or webcal link from Google, Apple or Outlook. Events are read-only here."))
        form=QVBoxLayout(); root.addLayout(form)
        self.name=QLineEdit(); self.url=QLineEdit(); self.every=QLineEdit("60")
        for label,field in (("Name",self.name),("Link",self.url),("Check every (min)",self.every)):
            row=QHBoxLayout(); row.addWidget(QLabel(label)); row.addWidget(field); form.addLayout(row)
        buttons=QDialogButtonBox()
        save=buttons.addButton("Save and sync",QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        save.clicked.connect(self._save); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        _show(self,parent)

    def _save(self):
        try:
            name=self.name.text().strip()
            if not name:raise ValueError("Give the calendar a name.")
            url=normalize_url(self.url.text()); every=int(self.every.text() or 60)
            if every<5:raise ValueError("Check at least every 5 minutes.")
        except ValueError as exc:
            QMessageBox.critical(self,"Check the link",str(exc));return
        sub=Subscription.new(name,url,every);self.cal.save_subscription(sub);self.cal.start_sync(sub.id);self.accept()


class SubscriptionsWindow(QDialog):
    def __init__(self,parent:QWidget,cal):
        super().__init__(parent);self.cal=cal;self.setWindowTitle("Calendar links")
        root=QVBoxLayout(self)
        root.addWidget(QLabel("Keep calendars from Google, Apple or Outlook up to date. Their events are read-only here."))
        from PyQt6.QtWidgets import QTableWidget,QTableWidgetItem
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(["Name","Every","Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);root.addWidget(self.table)
        self._items=QTableWidgetItem
        row=QHBoxLayout();root.addLayout(row)
        for text,fn in (("Add link",self.add),("Sync now",self.sync_now),("Remove",self.remove),("Close",self.accept)):
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        self._subs=[("calendar.subscriptions.changed",self._refresh),("calendar.synced",self._refresh)]
        for pattern,handler in self._subs:cal.api.on(pattern,handler)
        self.finished.connect(self._cleanup);self._refresh();_show(self,parent)

    @staticmethod
    def _status(s:Subscription)->str:
        if s.last_error:return f"Problem: {s.last_error[:60]}"
        if s.last_sync:return f"Up to date · checked {s.last_sync:%b %d, %H:%M}"
        return "Checking…" if s.last_attempt else "Not checked yet"

    def _refresh(self,*_a,**_k):
        from PyQt6.QtWidgets import QTableWidgetItem
        self.table.setRowCount(0)
        for s in self.cal.subscriptions():
            row=self.table.rowCount();self.table.insertRow(row)
            for col,text in enumerate((s.name,f"{s.interval_min} min",self._status(s))):
                self.table.setItem(row,col,QTableWidgetItem(text))
            self.table.item(row,0).setData(Qt.ItemDataRole.UserRole,s.id)

    def _selected_id(self):
        row=self.table.currentRow()
        return self.table.item(row,0).data(Qt.ItemDataRole.UserRole) if row>=0 else None

    def _cleanup(self):
        for pattern,handler in self._subs:self.cal.api.off(pattern,handler)

    def add(self):SubscriptionDialog(self,self.cal)
    def sync_now(self):
        if self._selected_id():self.cal.start_sync(self._selected_id())
    def remove(self):
        sub_id=self._selected_id()
        if sub_id and QMessageBox.question(self,"Remove link","Remove this calendar link and its events?")==QMessageBox.StandardButton.Yes:
            self.cal.remove_subscription(sub_id)
