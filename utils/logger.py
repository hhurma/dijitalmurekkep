import logging
import sys

# İleride log dosyasının yolu ve formatı buradan ayarlanabilir
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
# Log seviyesini DEBUG olarak değiştir
LOG_LEVEL = logging.DEBUG

def setup_logging():
    """Temel logging yapılandırmasını ayarlar."""
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT, stream=sys.stdout)
    # Dosyaya loglama da ekle:
    file_handler = logging.FileHandler("app.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    logging.info("Logging yapılandırması tamamlandı.")