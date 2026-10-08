"""Portable entry point; the implementation ships inside the standalone skill."""
from pathlib import Path
import sys

_SCRIPTS = Path(__file__).resolve().parent / ".agents/skills/translate-book/scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from book_model_selection import *  # noqa: F403
