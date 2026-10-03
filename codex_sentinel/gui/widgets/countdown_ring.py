from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from codex_sentinel.gui.common import tr


class CountdownRing(QWidget):
    """Circular progress ring showing countdown time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.total_seconds = 0
        self.remaining_seconds = 0
        self.setMinimumSize(200, 200)

    def set_countdown(self, total: int, remaining: int):
        self.total_seconds = max(1, total)
        self.remaining_seconds = max(0, remaining)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(10, 10, self.width() - 20, self.height() - 20)

        # Background ring
        bg_pen = QPen(QColor("#313244"), 15)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Progress ring
        if self.total_seconds > 0:
            progress = min(1, self.remaining_seconds / self.total_seconds)
            span_angle = int(-360 * progress * 16)

            # Color gradient from amber to green
            if progress > 0.5:
                color = QColor("#f59e0b")  # Amber
            else:
                color = QColor("#a6e3a1")  # Green

            prog_pen = QPen(color, 15)
            prog_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(prog_pen)
            painter.drawArc(rect, 90 * 16, span_angle)

        # Text
        painter.setPen(QColor("#cdd6f4"))
        font = QFont("Arial", 24, QFont.Weight.Bold)
        painter.setFont(font)

        mins, secs = divmod(self.remaining_seconds, 60)
        hours, mins = divmod(mins, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, time_str)

        font = QFont("Arial", 10)
        painter.setFont(font)
        painter.drawText(
            rect.adjusted(0, 40, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            tr("距记录的重置时间", "until recorded reset"),
        )
