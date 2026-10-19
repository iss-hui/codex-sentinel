"""Small shared native widgets for the approved A desktop layout."""

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QLayout,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from codex_sentinel.gui.theme import colors


def label(text="", role="muted", selectable=False):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    if selectable:
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def card(title=""):
    widget = QFrame()
    widget.setObjectName("panel")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(15)
    if title:
        layout.addWidget(label(title, "section"))
    return widget, layout


def heading(layout, title, subtitle):
    layout.addWidget(label(title, "heading"))
    layout.addWidget(label(subtitle, "muted"))
    layout.addSpacing(10)


def field(title, control):
    widget = QWidget()
    widget.setObjectName("fieldWrapper")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    layout.addWidget(label(title))
    if isinstance(control, QLayout):
        layout.addLayout(control)
    else:
        layout.addWidget(control)
    return widget


def tone(widget, value):
    if widget.property("tone") != value:
        widget.setProperty("tone", value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


_PATHS = {
    "overview": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 5h3"/>',
    "queue": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "chat": '<path d="M21 11a8 8 0 0 1-8 8H6l-4 3V11a9 9 0 0 1 19 0Z"/><path d="M7 10h10M7 14h6"/>',
    "settings": '<path d="m9 3-1 3-3 1-2 3 2 2-1 4 3 2 3-1 3 3 3-2 1-3 3-1v-4l-3-1-1-3-4-1-2-2Z"/><circle cx="12" cy="12" r="3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
    "moon": '<path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z"/>',
    "shield": '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
}


def outline_icon(name, color):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</svg>'
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class Toggle(QCheckBox):
    """Native checkbox behavior and accessibility, with the approved switch shape."""

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 48, 28)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        c = colors(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(c["muted"] if self.isEnabled() else c["dim"]))
        painter.drawText(
            self.rect().adjusted(0, 0, -40, 0),
            Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        x, y = self.width() - 30, (self.height() - 16) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["primary"] if self.isChecked() else c["border"]))
        painter.drawRoundedRect(QRectF(x, y, 29, 16), 8, 8)
        painter.setBrush(QColor("#ffffff" if self.isChecked() else c["muted"]))
        painter.drawEllipse(QRectF(x + (15 if self.isChecked() else 3), y + 3, 10, 10))
        if self.hasFocus():
            painter.setPen(QColor(c["blue"]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 3, 3)


STATUS_ROLE = Qt.ItemDataRole.UserRole + 1


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        opt.widget.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )
        c = colors(opt.widget)
        code = index.data(STATUS_ROLE)
        role = (
            "success"
            if code in ("completed", "simulated")
            else "error"
            if code in ("failed", "error", "interrupted")
            else "warning"
            if code in ("rate_limited", "waiting", "missed", "awaiting_limit")
            else None
        )
        foreground, background = (
            (c[role], c[role + "_bg"])
            if role
            else (c["blue"], c["selected"])
            if code in ("pending", "running")
            else (c["muted"], c["hover"])
        )
        rect = QRectF(opt.rect).adjusted(6, 10, -6, -10)
        rect.setWidth(min(rect.width(), opt.fontMetrics.horizontalAdvance(text) + 16))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(foreground))
        painter.drawText(
            rect.adjusted(7, 0, -5, 0),
            Qt.AlignmentFlag.AlignVCenter,
            opt.fontMetrics.elidedText(
                text, Qt.TextElideMode.ElideRight, int(rect.width() - 12)
            ),
        )
        painter.restore()
