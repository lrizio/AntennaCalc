"""Importing this module registers every antenna model."""
from . import models_wire  # noqa: F401
try:
    from . import models_vert  # noqa: F401
    from . import models_beam  # noqa: F401
    from . import models_vhf  # noqa: F401
    from . import models_analytic  # noqa: F401
    from . import models_arrays  # noqa: F401
except ImportError:
    pass
from .design import REGISTRY, CATEGORIES, enable_wide_sweep, specs_in  # noqa: F401

# HF antennas whose behaviour across the whole HF range is worth seeing (harmonics, multi-band use)
for _k in ("dipole", "ocfd", "g5rv", "fan", "trap_dipole", "longwire", "efhw", "zepp", "hloop", "delta",
           "lazyh", "trap_vert", "marconi", "vhw", "gp", "loaded_dipole", "stealth", "loaded"):
    if _k in REGISTRY:
        enable_wide_sweep(REGISTRY[_k], default=(_k == "efhw"))
