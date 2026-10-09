"""Background design worker."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from .. import engine


class DesignWorker(QThread):
    progress = Signal(float, str)
    finished_ok = Signal(object, dict)
    failed = Signal(str)

    def __init__(self, spec, req, ex, basis, scales=None, optimise_only=False, parent=None):
        super().__init__(parent)
        self.spec, self.req, self.ex, self.basis = spec, req, dict(ex), basis
        self.scales = dict(scales or {})
        self.optimise_only = optimise_only
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _stage(self, lo, hi):
        def cb(frac, text):
            self.progress.emit(lo + (hi - lo) * max(0.0, min(1.0, frac)), text)
        return cb

    def run(self):
        spec, req = self.spec, self.req
        cancel = lambda: self._cancel
        try:
            notes = []
            ex = self.ex
            scales = dict(self.scales)
            if not self.optimise_only and spec.auto_key and req.target_gain is not None:
                self.progress.emit(0.01, "Choosing the size for the gain target...")
                ex, notes = engine.auto_design(spec, req, ex, self.basis, self._stage(0.0, 0.1), cancel,
                                               margin=0.7 if (req.optimize and spec.optimizable) else 0.0)
                scales = {}
            if not spec.analytic and req.auto_tune and not self.optimise_only:
                scales = engine.tune(spec, req, ex, scales, self._stage(0.1, 0.35), cancel)
            if spec.optimizable and (req.optimize or self.optimise_only):
                scales = engine.optimize(spec, req, ex, scales, self._stage(0.35, 0.65), cancel, maxiter=70)
                if req.auto_tune or self.optimise_only:
                    scales = engine.tune(spec, req, ex, scales, self._stage(0.65, 0.7), cancel)
            res = engine.evaluate(spec, req, ex, scales, self._stage(0.7, 1.0), cancel)
            res.ex = dict(ex)
            res.basis = self.basis
            if req.target_gain is not None and self.basis == "free":
                res.free_gain = engine.free_space_gain(spec, req, ex, scales)
            for n in reversed(notes):
                res.design.notes.insert(0, n)
            self.finished_ok.emit(res, ex)
        except engine.Cancelled:
            self.failed.emit("Cancelled.")
        except Exception as e:      # surface any model error to the user
            self.failed.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=6)}")
