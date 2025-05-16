"""GUI ile ilgili enum tanımlamaları."""
from enum import Enum, auto

class TemplateType(Enum):
    PLAIN = auto()
    LINED = auto()
    GRID = auto()
    LINES_AND_GRID = auto()
    DOT_GRID = auto()

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
    # --- YENİ: Düzenlenebilir Çizgi Aracı --- #
    EDITABLE_LINE = auto()
    # --- YENİ: Düzenlenebilir Çizgi Düzenleme Aracı --- #
    EDITABLE_LINE_EDITOR = auto()
    # --- YENİ: Düzenlenebilir Çizgi Kontrol Noktası Seçici --- #
    EDITABLE_LINE_NODE_SELECTOR = auto()
    # --- YENİ: PATH Aracı --- #
    PATH = auto()
    # --- --- --- --- --- --- --- --- -- #

class Orientation(Enum):
    PORTRAIT = auto() # Dikey
    LANDSCAPE = auto() # Yatay 