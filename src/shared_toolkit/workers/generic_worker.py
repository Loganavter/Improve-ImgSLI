import sys
import traceback

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)

class GenericWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(GenericWorker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:

            if not (isinstance(e, RuntimeError) and str(e) == "Save canceled by user"):
                traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:

            if not (result is None):
                self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
