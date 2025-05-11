import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QScreen

from gui.arayuz import MainWindow
from utils.logger import setup_logging
import build_info


def main():
    """Uygulamanın ana giriş noktası."""
    setup_logging() # Logger'ı başlat
    logging.info("Uygulama başlatılıyor...")

    app = QApplication(sys.argv)

    # Font Awesome ikon fontunu yükle (varsa)
    # gui.utils.load_fonts() # Bu fonksiyon varsa çağrılabilir

    # YENİ: Derleme zamanını logla
    logging.info(f"Uygulama Başlatıldı - Derleme Zamanı: {build_info.BUILD_TIMESTAMP}")

    # Ana pencere oluşturulacak
    window = MainWindow()
    
    # --- YENİ: Pencereyi Ortala --- #
    try:
        # Ana ekranı al
        primary_screen = QScreen.availableGeometry(QApplication.primaryScreen())
        # Pencere boyutunu al (henüz show() çağrılmadığı için frameGeometry daha iyi olabilir)
        window_geometry = window.frameGeometry()
        # Merkez pozisyonunu hesapla
        center_point = primary_screen.center() - window_geometry.center()
        # Pencereyi taşı
        window.move(center_point)
        logging.debug(f"Pencere ortalandı: {center_point}")
    except Exception as e:
        logging.error(f"Pencere ortalanırken hata: {e}")
    # --- --- --- --- --- --- --- -- #

    window.show()

    logging.info("Uygulama arayüzü gösteriliyor.")
    # print("Ana pencere (MainWindow) henüz implemente edilmedi.") # Kaldırıldı

    # Olay döngüsünü başlat
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 