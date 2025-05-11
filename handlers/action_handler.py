# handlers/action_handler.py
import logging

# Gerekli importlar buraya eklenecek
# from utils.undo_redo_manager import UndoRedoManager

def handle_undo(undo_manager):
    """Undo işlemini tetikler."""
    if undo_manager:
        logging.debug("Handling undo action...")
        undo_manager.undo()
    else:
        # Aktif sayfa olmadığında veya manager None ise bu durum oluşabilir.
        # MainWindow'daki _update_active_page_connections kontrol ettiği için buraya gelmemeli.
        logging.warning("handle_undo çağrıldı ancak undo_manager None veya mevcut değil.")

def handle_redo(undo_manager):
    """Redo işlemini tetikler."""
    if undo_manager:
        logging.debug("Handling redo action...")
        undo_manager.redo()
    else:
        logging.warning("handle_redo çağrıldı ancak undo_manager None veya mevcut değil.") 