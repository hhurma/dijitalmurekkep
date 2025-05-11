"""GUI ile ilgili enum tanımlamaları."""
from enum import Enum, auto

class TemplateType(Enum):
    PLAIN = auto()
    LINED = auto()
    GRID = auto()

class ToolType(Enum):
    """Kullanılabilir çizim araçları."""
    PEN = auto()
    LINE = auto()
    RECTANGLE = auto()
    CIRCLE = auto()
    ERASER = auto() # Silgi eklendi
    SELECTOR = auto() # Seçim aracı da ekleyelim 
    # --- YENİ İşaretçi Araçları ---
    LASER_POINTER = auto()
    TEMPORARY_POINTER = auto()
    # --- YENİ: Resim Seçim Aracı --- #
    IMAGE_SELECTOR = auto()
    # --- --- --- --- --- --- --- --- -- #

class Orientation(Enum):
    PORTRAIT = auto() # Dikey
    LANDSCAPE = auto() # Yatay 