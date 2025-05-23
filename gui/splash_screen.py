import sys
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import QWidget, QApplication
import math

class SplashScreen(QWidget):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            print(f"Splash görseli yüklenemedi: {image_path}")
        self.setFixedSize(420, 420)
        self.text = "Yükleniyor..."
        self.font = QFont("Arial", 18, QFont.Weight.Bold)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Arka plan (tamamı #f8f8f8, köşeler yuvarlatılmış)
        painter.setBrush(QColor(248, 248, 248))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 24, 24)
        # Logo
        if not self.pixmap.isNull():
            x, y, w, h = 60, 40, 300, 300
            painter.drawPixmap(x, y, w, h, self.pixmap)
        # Yükleniyor metni (biraz daha yukarıda)
        painter.setFont(self.font)
        painter.setPen(QColor(30, 40, 80))
        painter.drawText(QRectF(0, 360, 420, 30), Qt.AlignmentFlag.AlignCenter, self.text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash = SplashScreen("splash.png")
    splash.show()
    QTimer.singleShot(3000, splash.close)  # 3 saniye sonra otomatik kapanır
    sys.exit(app.exec()) 