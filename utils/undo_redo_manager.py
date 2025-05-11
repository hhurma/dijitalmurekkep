from PyQt6.QtCore import QObject, pyqtSignal
import logging
# import time # time modülünü import et - KALDIRILDI
from .commands import Command # Aynı dizindeki commands modülünden import et
# --- YENİ: QApplication importu (processEvents için) ---
from PyQt6.QtWidgets import QApplication # YENİ - KALDIRILDI
# --- --- --- --- --- --- --- --- --- --- --- --- ---

class UndoRedoManager(QObject):
    """Undo/Redo yığınlarını ve işlemlerini yönetir."""

    # Sinyaller: Undo/Redo durumundaki değişiklikleri bildirmek için
    can_undo_changed = pyqtSignal(bool)
    can_redo_changed = pyqtSignal(bool)
    content_modified = pyqtSignal() # İçerik değiştiğinde yayınlanır

    def __init__(self, parent=None):
        super().__init__(parent)
        self.undo_stack = []
        self.redo_stack = []
        self._is_processing = False # YENİ: İşlem devam ediyor mu bayrağı
        logging.info("UndoRedoManager başlatıldı.")

    def execute(self, command: Command):
        """Yeni bir komutu çalıştırır ve undo yığınına ekler."""
        if self._is_processing: # Ekleme: Eğer işlem devam ediyorsa yeni komut ekleme
            logging.warning("Execute: İşlem devam ederken çağrıldı, yeni komut yoksayıldı.")
            return
            
        self._is_processing = True
        try:
            logging.debug(f"[UndoRedoManager] execute çağrıldı. Komut: {type(command).__name__}")
            result = command.execute()
            if result is False:
                logging.warning(f"[UndoRedoManager] Komut execute başarısız: {type(command).__name__}")
                return False
            self.undo_stack.append(command)
            self.redo_stack.clear() # Yeni komut sonrası redo yığınını temizle
            logging.debug(f"[UndoRedoManager] Komut yığına eklendi. Undo stack uzunluğu: {len(self.undo_stack)}")
            self._emit_stack_signals()
            logging.debug(f"Komut yürütüldü ve undo yığınına eklendi: {type(command).__name__}")
            self.content_modified.emit() # İçerik değişti
            return True
        except Exception as e:
            logging.error(f"Komut execute edilirken hata oluştu: {type(command).__name__} - {e}")
        finally:
             self._is_processing = False # İşlemi bitir

    def undo(self):
        """Son komutu geri alır."""
        # YENİ LOGLAR BAŞLANGIÇ
        command_on_top = self.undo_stack[-1] if self.undo_stack else None
        canvas_shapes_content = 'Canvas/Shapes Bilgisi Yok'
        if command_on_top and hasattr(command_on_top, 'canvas') and hasattr(command_on_top.canvas, 'shapes'):
            canvas_shapes_content = f"Canvas.shapes id={id(command_on_top.canvas.shapes)}, içerik={command_on_top.canvas.shapes}"
        logging.debug(f"UndoRedoManager.undo: BAŞLANGIÇ. Undo yığını (ilk öğe eğer varsa): {type(command_on_top).__name__ if command_on_top else 'BOŞ'}. {canvas_shapes_content}")
        # YENİ LOGLAR BİTİŞ

        if not self.can_undo() or self._is_processing:
            if self._is_processing: logging.warning("Undo: İşlem devam ederken çağrıldı, yoksayıldı.")
            return

        self._is_processing = True
        command_undone_successfully = False
        command_type_name = "Unknown"
        command_to_redo = None
        try:
            command = self.undo_stack.pop()
            command_type_name = type(command).__name__
            # YENİ LOG
            # logging.debug(f"UndoRedoManager.undo: Komut YIĞINDAN ALINDI: {command_type_name}. Canvas.shapes id={id(command.canvas.shapes)}, içerik={command.canvas.shapes}")
            
            # YENİ LOG
            # logging.debug(f"UndoRedoManager.undo: {command_type_name}.undo() ÇAĞRILMADAN ÖNCE. Canvas.shapes id={id(command.canvas.shapes)}, içerik={command.canvas.shapes}")
            command.undo()
            # YENİ LOG
            # logging.debug(f"UndoRedoManager.undo: {command_type_name}.undo() ÇAĞRILDIKTAN SONRA. Canvas.shapes id={id(command.canvas.shapes)}, içerik={command.canvas.shapes}")
             
            command_undone_successfully = True
            command_to_redo = command

        except Exception as e:
             logging.error(f"Undo işlemi sırasında hata: {command_type_name} - {e}", exc_info=True)
             command_to_redo = command # Hataya rağmen redo yığınına ekle
        finally:
            if command_to_redo:
                self.redo_stack.append(command_to_redo)
                self._emit_stack_signals()
                # logging.debug(f"Komut {command_type_name} geri alındı (başarı={command_undone_successfully}) ve redo yığınına eklendi.")
                self.content_modified.emit()
            
            self._is_processing = False

    def redo(self):
        """Geri alınmış son komutu yeniden uygular."""
        if not self.can_redo() or self._is_processing:
            if self._is_processing: logging.warning("Redo: İşlem devam ederken çağrıldı, yoksayıldı.")
            # else: logging.debug("Yeniden uygulanacak komut yok.")
            return
            
        self._is_processing = True
        command_redone_successfully = False
        command_type_name = "Unknown"
        command_to_undo = None
        try:
            command = self.redo_stack.pop()
            command_type_name = type(command).__name__
            # logging.debug(f"Redo: Popped command {command_type_name} from redo_stack.")
            command.execute()
            command_redone_successfully = True # Varsayım
            command_to_undo = command
        except Exception as e:
            logging.error(f"Redo işlemi sırasında hata: {command_type_name} - {e}", exc_info=True)
            command_to_undo = command
        finally:
            if command_to_undo:
                 self.undo_stack.append(command_to_undo)
                 self._emit_stack_signals()
                #  logging.debug(f"Komut {command_type_name} yeniden uygulandı (başarı={command_redone_successfully}) ve undo yığınına eklendi.")
                 self.content_modified.emit()
                 
            self._is_processing = False

    def can_undo(self) -> bool:
        """Geri alınacak komut olup olmadığını kontrol eder."""
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        """İleri alınacak komut olup olmadığını kontrol eder."""
        return bool(self.redo_stack)

    def clear_stacks(self):
        """Undo ve Redo yığınlarını temizler."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._emit_stack_signals()
        # logging.info("Undo/Redo yığınları temizlendi.")

    def _emit_stack_signals(self):
        """Yığın durumuna göre can_undo/can_redo sinyallerini tetikler."""
        logging.debug(f"UndoRedoManager._emit_stack_signals: BAŞLANGIÇ. can_undo={self.can_undo()}, can_redo={self.can_redo()}")
        self.can_undo_changed.emit(self.can_undo())
        self.can_redo_changed.emit(self.can_redo())
        # logging.debug(f"UndoRedoManager._emit_stack_signals: BİTİŞ.")

    # ... mevcut kod ... 