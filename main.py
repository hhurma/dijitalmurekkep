import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QScreen

from gui.arayuz import MainWindow
from utils.logger import setup_logging
import build_info
from gui.splash_screen import SplashScreen


def main():
    """Uygulamanın ana giriş noktası."""
    setup_logging() # Logger'ı başlat
    logging.info("Uygulama başlatılıyor...")

    app = QApplication(sys.argv)

    # Splash ekranı başlat
    splash = SplashScreen("splash.png")
    splash.show()
    app.processEvents()  # Splash'ın hemen görünmesi için

    def show_main_window():
        # Ana pencere oluşturulacak
        window = MainWindow()
        try:
            primary_screen = QScreen.availableGeometry(QApplication.primaryScreen())
            window_geometry = window.frameGeometry()
            center_point = primary_screen.center() - window_geometry.center()
            window.move(center_point)
        except Exception as e:
            logging.error(f"Pencere ortalanırken hata: {e}")
        splash.close()
        window.show()
        logging.info("Uygulama arayüzü gösteriliyor.")

    # Splash en az 2 saniye görünsün
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(2000, show_main_window)

    # Font Awesome ikon fontunu yükle (varsa)
    # gui.utils.load_fonts() # Bu fonksiyon varsa çağrılabilir

    # YENİ: Derleme zamanını logla
    logging.info(f"Uygulama Başlatıldı - Derleme Zamanı: {build_info.BUILD_TIMESTAMP}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main() 