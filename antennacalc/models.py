"""Importing this module registers every antenna model."""
from . import models_wire  # noqa: F401
try:
    from . import models_vert  # noqa: F401
    from . import models_beam  # noqa: F401
    from . import models_vhf  # noqa: F401
    from . import models_analytic  # noqa: F401
except ImportError:
    pass
from .design import REGISTRY, CATEGORIES, specs_in  # noqa: F401
