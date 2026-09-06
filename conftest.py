"""Dev convenience: if contragent is not installed, fall back to the
sibling checkout (../ContrAgent). Proper setup is documented in README:

    pip install -e ../ContrAgent
"""

import pathlib
import sys

try:
    import contragent  # noqa: F401
except ModuleNotFoundError:
    sibling = pathlib.Path(__file__).resolve().parent.parent / "ContrAgent"
    if (sibling / "contragent").exists():
        sys.path.insert(0, str(sibling))
