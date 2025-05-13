# main.py
import sys
import time
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPainter, QPen, QColor, QMouseEvent, QPaintEvent, QPainterPath
from PyQt6.QtCore import Qt, QTimer, QPointF

class GlowTrailCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Glow Trail Demo")
        self.setGeometry(100, 100, 800, 600)
        self.trail_points = []  # (QPointF, timestamp)
        self.trail_duration = 1.2  # Saniye
        self.drawing = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_trail)
        self.timer.start(20)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.trail_points = [(event.position(), time.time())]
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drawing:
            self.trail_points.append((event.position(), time.time()))
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False

    def update_trail(self):
        now = time.time()
        # Sadece trail_duration süresi kadar eski noktaları tut
        self.trail_points = [(p, t) for (p, t) in self.trail_points if now - t < self.trail_duration]
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.trail_points) < 2:
            return

        # Glow efekti: Çok katmanlı, dıştan içe
        for glow in range(8, 0, -1):
            path = QPainterPath()
            path.moveTo(self.trail_points[0][0])
            for p, _ in self.trail_points[1:]:
                path.lineTo(p)
            alpha = int(60 * (glow / 8.0))
            width = 18 * (glow / 8.0)
            color = QColor(255, 80, 80, alpha)
            pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # Ana çizgi (beyaz, daha ince)
        path = QPainterPath()
        path.moveTo(self.trail_points[0][0])
        for p, _ in self.trail_points[1:]:
            path.lineTo(p)
        pen = QPen(QColor(255, 255, 255, 220), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # Fade-out: Noktalar yaşlandıkça siliniyor (update_trail ile)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = GlowTrailCanvas()
    w.show()
    sys.exit(app.exec())