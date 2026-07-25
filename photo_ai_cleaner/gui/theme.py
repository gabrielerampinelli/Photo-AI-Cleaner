"""Light and dark themes implemented as Qt style sheets."""

from __future__ import annotations

_DARK = """
* { font-family: "Segoe UI", sans-serif; font-size: 10pt; }
QMainWindow, QDialog, QWidget { background-color: #1e1f22; color: #e6e6e6; }
QLineEdit, QSpinBox, QComboBox, QDateEdit {
    background-color: #2b2d31; border: 1px solid #3a3d43; border-radius: 6px;
    padding: 6px 8px; color: #e6e6e6;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #5865f2; }
QPushButton {
    background-color: #3a3d43; border: none; border-radius: 6px;
    padding: 8px 14px; color: #e6e6e6;
}
QPushButton:hover { background-color: #4a4d54; }
QPushButton:pressed { background-color: #5865f2; }
QPushButton#primary { background-color: #5865f2; color: white; font-weight: 600; }
QPushButton#primary:hover { background-color: #6873f5; }
QPushButton#danger { background-color: #b0413e; color: white; }
QPushButton#danger:hover { background-color: #c74e4a; }
QListWidget { background-color: #232428; border: none; }
QListWidget::item { color: #e6e6e6; }
QListWidget::item:selected { background-color: #3a3d5a; border: 1px solid #5865f2; }
QProgressBar {
    background-color: #2b2d31; border: none; border-radius: 6px; text-align: center;
    color: #e6e6e6; height: 18px;
}
QProgressBar::chunk { background-color: #5865f2; border-radius: 6px; }
QLabel#header { font-size: 12pt; font-weight: 600; color: #ffffff; }
QLabel#status { color: #9aa0a6; }
QStatusBar { background-color: #17181b; color: #9aa0a6; }
QMenuBar, QMenu { background-color: #1e1f22; color: #e6e6e6; }
QMenu::item:selected { background-color: #3a3d5a; }
"""

_LIGHT = """
* { font-family: "Segoe UI", sans-serif; font-size: 10pt; }
QMainWindow, QDialog, QWidget { background-color: #f5f6f8; color: #1a1a1a; }
QLineEdit, QSpinBox, QComboBox, QDateEdit {
    background-color: #ffffff; border: 1px solid #d0d3d9; border-radius: 6px;
    padding: 6px 8px; color: #1a1a1a;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #5865f2; }
QPushButton {
    background-color: #e4e6eb; border: none; border-radius: 6px;
    padding: 8px 14px; color: #1a1a1a;
}
QPushButton:hover { background-color: #d8dae0; }
QPushButton:pressed { background-color: #c3c6ce; }
QPushButton#primary { background-color: #5865f2; color: white; font-weight: 600; }
QPushButton#primary:hover { background-color: #6873f5; }
QPushButton#danger { background-color: #d9534f; color: white; }
QPushButton#danger:hover { background-color: #e0625e; }
QListWidget { background-color: #ffffff; border: 1px solid #e0e2e7; }
QListWidget::item { color: #1a1a1a; }
QListWidget::item:selected { background-color: #dfe3ff; border: 1px solid #5865f2; }
QProgressBar {
    background-color: #e4e6eb; border: none; border-radius: 6px; text-align: center;
    color: #1a1a1a; height: 18px;
}
QProgressBar::chunk { background-color: #5865f2; border-radius: 6px; }
QLabel#header { font-size: 12pt; font-weight: 600; color: #111111; }
QLabel#status { color: #6b7076; }
QStatusBar { background-color: #e9ebef; color: #6b7076; }
"""


def stylesheet_for(theme: str) -> str:
    """Return the Qt style sheet for ``"dark"`` or ``"light"``."""
    return _LIGHT if theme.lower() == "light" else _DARK
