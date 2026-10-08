"""Shared application logo for source and bundled desktop launches."""
from pathlib import Path

from PySide6.QtGui import QIcon


def application_icon():
    return QIcon(str(Path(__file__).with_name("assets") / "logo.png"))
