import sys
import traceback

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)
    partial_result = pyqtSignal(object)

class GenericWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(GenericWorker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def _safe_emit(self, signal_name: str, *args):
        try:
            signal = getattr(self.signals, signal_name, None)
            if signal is not None:
                signal.emit(*args)
        except RuntimeError as exc:
            if "wrapped C/C++ object of type WorkerSignals has been deleted" not in str(
                exc
            ):
                raise

    @pyqtSlot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:

            if not (isinstance(e, RuntimeError) and str(e) == "Save canceled by user"):
                traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self._safe_emit("error", (exctype, value, traceback.format_exc()))
        else:

            if not (result is None):
                self._safe_emit("result", result)
        finally:
            self._safe_emit("finished")
