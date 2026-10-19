"""Shared neutral desktop themes; no scheduler or execution state lives here."""

import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "dark": {
        "canvas": "#141414",
        "sidebar": "#181818",
        "panel": "#1f1f1f",
        "raised": "#252525",
        "text": "#f1f1f1",
        "muted": "#b0b0b0",
        "dim": "#969696",
        "border": "#363636",
        "soft": "#2d2d2d",
        "blue": "#79b8ff",
        "selected": "#21334a",
        "primary": "#176cce",
        "hover": "#2b2b2b",
        "primary_hover": "#1e70cc",
        "input": "#181818",
        "warning": "#e9bd78",
        "warning_bg": "#3b3021",
        "success": "#9dceae",
        "success_bg": "#24332a",
        "error": "#f39b9b",
        "error_bg": "#402929",
    },
    "light": {
        "canvas": "#f6f6f6",
        "sidebar": "#fafafa",
        "panel": "#ffffff",
        "raised": "#f6f6f6",
        "text": "#202020",
        "muted": "#5c5c5c",
        "dim": "#6b6b6b",
        "border": "#d5d5d5",
        "soft": "#e7e7e7",
        "blue": "#0865be",
        "selected": "#e8f1fc",
        "primary": "#0865be",
        "hover": "#eeeeee",
        "primary_hover": "#0756a3",
        "input": "#ffffff",
        "warning": "#8a5508",
        "warning_bg": "#fff3dd",
        "success": "#26713e",
        "success_bg": "#eaf4ed",
        "error": "#b53434",
        "error_bg": "#fcecec",
    },
}


def resolved_theme(choice):
    if choice == "system":
        return (
            "dark"
            if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
            else "light"
        )
    return choice if choice in COLORS else "dark"


def colors(widget):
    while widget is not None:
        theme = widget.property("effectiveTheme")
        if theme in COLORS:
            return COLORS[theme]
        widget = widget.parentWidget()
    return COLORS["dark"]


def stylesheet(theme):
    assets = Path(__file__).with_name("assets")
    c = {
        **COLORS[theme],
        "arrow": (assets / f"chevron-{theme}.svg").as_posix(),
        "up_arrow": (assets / f"chevron-up-{theme}.svg").as_posix(),
        "check": (assets / "check.svg").as_posix(),
    }
    return Template("""
    QWidget { background: $canvas; color: $text; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; }
    QMainWindow { background: $canvas; }
    QDialog { background: $panel; }
    QWidget#sidebar, QWidget#toolbar, QStatusBar { background: $sidebar; }
    QWidget#sidebar { border-right: 1px solid $soft; }
    QWidget#toolbar { border-bottom: 1px solid $soft; }
    QFrame#panel { background: $panel; border: 1px solid $border; border-radius: 9px; }
    QWidget#fieldWrapper, QWidget#sidebar QLabel, QWidget#toolbar QLabel { background: transparent; }
    QLabel { background: transparent; border: none; }
    QLabel#heading { color: $text; font-size: 26px; font-weight: 600; }
    QLabel#section { color: $text; font-size: 14px; font-weight: 600; }
    QLabel#target { color: $text; font-size: 21px; font-weight: 600; }
    QLabel#muted { color: $muted; }
    QLabel#hint, QLabel#eyebrow { color: $dim; font-size: 11px; }
    QLabel#path { color: $muted; font-family: 'Consolas', monospace; font-size: 11px; }
    QLabel#clock { color: $text; font-family: 'Consolas', monospace; font-size: 43px; font-weight: 500; }
    QLabel#quotaValue { color: $text; font-family: 'Consolas', monospace; font-size: 31px; }
    QLabel#activationStatus { color: $blue; font-size: 17px; font-weight: 500; }
    QLabel#pill { color: $blue; background: $selected; padding: 5px 8px; border-radius: 4px; font-size: 11px; }
    QLabel[tone="warning"] { color: $warning; }
    QLabel[tone="success"] { color: $success; }
    QLabel[tone="error"] { color: $error; }
    QPushButton { background: $panel; border: 1px solid $border; border-radius: 5px; padding: 7px 11px; color: $text; }
    QPushButton:hover { background: $hover; }
    QPushButton:pressed { background: $selected; }
    QPushButton:focus { border-color: $blue; }
    QPushButton:disabled { color: $dim; background: $raised; border-color: $soft; }
    QPushButton#primary { background: $primary; border-color: $primary; color: white; font-weight: 600; }
    QPushButton#primary:hover { background: $primary_hover; }
    QPushButton#textButton { color: $blue; border: none; background: transparent; }
    QLabel#quotaValue:disabled { color: $dim; }
    QPushButton#primary:disabled { background: $raised; border-color: $soft; color: $dim; }
    QPushButton#brand { border: none; background: transparent; font-size: 20px; font-weight: 600; text-align: left; padding: 0; }
    QPushButton#nav { text-align: left; border: 1px solid transparent; background: transparent; padding: 12px 10px; color: $muted; }
    QPushButton#nav:hover { background: $hover; }
    QPushButton#nav:checked, QPushButton#mode:checked { background: $selected; color: $blue; border: 1px solid $blue; }
    QPushButton#mode { text-align: left; padding: 12px 14px; font-size: 12px; }
    QPushButton#themeButton, QPushButton#version { border: none; background: transparent; color: $muted; font-size: 11px; }
    QPushButton#newBadge { color: white; background: $primary; border: none; font-size: 10px; padding: 3px 5px; }
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox, QDateTimeEdit, QTextBrowser {
        background: $input; color: $text; border: 1px solid $border; border-radius: 5px; padding: 7px; selection-background-color: $primary; selection-color: white;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus { border-color: $blue; }
    QLineEdit:disabled, QDateTimeEdit:disabled, QSpinBox:disabled { color: $dim; background: $raised; }
    QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button, QDateTimeEdit::drop-down { border: none; width: 18px; }
    QComboBox::down-arrow, QDateTimeEdit::down-arrow { image: url("$arrow"); width: 10px; height: 10px; }
    QSpinBox::up-arrow { image: url("$up_arrow"); width: 8px; height: 8px; }
    QSpinBox::down-arrow { image: url("$arrow"); width: 8px; height: 8px; }
    QComboBox QAbstractItemView { background: $panel; color: $text; selection-background-color: $selected; selection-color: $text; padding: 4px; }
    QCheckBox { background: transparent; spacing: 8px; color: $muted; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid $dim; border-radius: 3px; background: $input; }
    QCheckBox::indicator:checked { background: $primary; border-color: $primary; image: url("$check"); }
    QProgressBar { border: none; border-radius: 2px; background: $border; min-height: 5px; max-height: 5px; }
    QProgressBar::chunk { background: $blue; border-radius: 2px; }
    QProgressBar[tone="warning"]::chunk { background: $warning; }
    QProgressBar:disabled::chunk { background: $dim; }
    QProgressBar#downloadProgress { min-height: 12px; max-height: 12px; }
    QTableWidget { background: $panel; alternate-background-color: $panel; color: $text; border: none; gridline-color: $soft; selection-background-color: $selected; selection-color: $text; }
    QTableWidget::item { padding: 7px; border-bottom: 1px solid $soft; }
    QTableWidget::item:selected { background: $selected; color: $text; }
    QHeaderView::section { background: $raised; color: $dim; font-size: 11px; border: none; border-bottom: 1px solid $soft; padding: 10px 7px; }
    QTableCornerButton::section { background: $raised; border: none; }
    QScrollArea { border: none; }
    QScrollBar:vertical { background: $canvas; width: 9px; margin: 0; }
    QScrollBar:horizontal { background: $canvas; height: 9px; margin: 0; }
    QScrollBar::handle { background: $border; border-radius: 4px; min-height: 25px; min-width: 25px; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: none; }
    QSplitter::handle { background: $canvas; height: 12px; }
    QMenu { background: $panel; color: $text; border: 1px solid $border; padding: 5px; }
    QMenu::item { padding: 8px 20px; }
    QMenu::item:selected { background: $selected; color: $blue; }
    QMenu::separator { height: 1px; background: $border; margin: 5px; }
    QToolTip { background: $panel; color: $text; border: 1px solid $border; padding: 6px; }
    QStatusBar { border-top: 1px solid $soft; color: $dim; font-size: 10px; }
    QStatusBar::item { border: none; }
    """).substitute(c)


DARK_STYLESHEET = stylesheet("dark")
LIGHT_STYLESHEET = stylesheet("light")


def apply_theme(window, choice):
    theme = resolved_theme(choice)
    c = COLORS[theme]
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, c["canvas"]),
        (QPalette.ColorRole.Base, c["input"]),
        (QPalette.ColorRole.AlternateBase, c["raised"]),
        (QPalette.ColorRole.Button, c["panel"]),
        (QPalette.ColorRole.Text, c["text"]),
        (QPalette.ColorRole.WindowText, c["text"]),
        (QPalette.ColorRole.ButtonText, c["text"]),
        (QPalette.ColorRole.Highlight, c["primary"]),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.PlaceholderText, c["dim"]),
        (QPalette.ColorRole.ToolTipBase, c["panel"]),
        (QPalette.ColorRole.ToolTipText, c["text"]),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c["dim"])
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c["dim"])
    )
    window.setProperty("effectiveTheme", theme)
    window.setPalette(palette)
    window.setStyleSheet(stylesheet(theme))
    if sys.platform == "win32" and QApplication.platformName() != "offscreen":
        # Keep the native title bar in sync without replacing Windows window controls.
        import ctypes

        try:
            dark = ctypes.c_int(theme == "dark")
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(window.winId()), 20, ctypes.byref(dark), ctypes.sizeof(dark)
            )
        except (OSError, AttributeError):
            pass
    return theme
