"""Shared visual tokens and application styling for the Qt frontend."""
from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

BG = "#FFF7E6"
SURFACE = "#FFFCF5"
DIM = "#F7EFD9"
TODAY_BG = "#FFF0B8"
INK = "#33261C"
MUTED = "#716151"
FAINT = "#76624C"
LINE = "#E8DDBF"
LINE_SOFT = "#F1E7C9"
CONTROL = "#F7EFD9"
CONTROL_HOVER = "#ECDEB7"
ACCENT = "#B63D24"
ACCENT_SOFT = "#FFE3CF"
ACCENT_INK = "#A52F18"
ACCENT_HOVER = "#A9321C"
ACCENT_BUTTON_TEXT = "#FFFFFF"
NOW = "#B42318"
SUCCESS = "#5C7D3A"
FAMILY = "sans-serif"
SIZE = 10
CURRENT_DENSITY = "comfortable"
DENSITY_OPTIONS = ("comfortable", "dense")
COLOR_FIELDS = ("background", "surface", "text", "accent")
PRESET_LABELS = {
    "warm": "Warm light",
    "dark": "Warm dark",
    "high_contrast": "High contrast",
    "custom": "Custom colors",
}
_PRESET_COLORS = {
    "warm": {
        "background": "#FFF7E6",
        "surface": "#FFFCF5",
        "text": "#33261C",
        "accent": "#B63D24",
    },
    "dark": {
        "background": "#201A17",
        "surface": "#2C2520",
        "text": "#F7EBDD",
        "accent": "#F07851",
    },
    "high_contrast": {
        "background": "#FFFFFF",
        "surface": "#FFFFFF",
        "text": "#111111",
        "accent": "#8F250F",
    },
}
_CURRENT_CONFIG = {"preset": "warm", **_PRESET_COLORS["warm"]}


def _contrast_ratio(foreground: QColor, background: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = (
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        )
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def theme_config(preset: str = "warm") -> dict[str, str]:
    try:
        return {"preset": preset, **_PRESET_COLORS[preset]}
    except KeyError:
        raise ValueError(f"Unknown theme preset: {preset}") from None


def normalize_theme(config: dict | None) -> dict[str, str]:
    if config is None:
        return theme_config()
    if not isinstance(config, dict):
        raise ValueError("The saved theme settings are invalid.")
    preset = config.get("preset", "warm")
    if isinstance(preset, str) and preset in _PRESET_COLORS:
        return theme_config(preset)
    if preset != "custom":
        raise ValueError(f"Unknown theme preset: {preset}")

    normalized = {"preset": "custom"}
    for field in COLOR_FIELDS:
        value = config.get(field)
        color = QColor(value) if isinstance(value, str) else QColor()
        if not color.isValid() or not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Choose a valid {field} color.")
        normalized[field] = color.name().upper()
    return normalized


def theme_errors(config: dict | None) -> list[str]:
    colors = normalize_theme(config)
    background = QColor(colors["background"])
    surface = QColor(colors["surface"])
    text = QColor(colors["text"])
    accent = QColor(colors["accent"])
    errors = []
    if min(_contrast_ratio(text, background), _contrast_ratio(text, surface)) < 4.5:
        errors.append("Text color must have at least 4.5:1 contrast against both background and surface.")
    if min(_contrast_ratio(accent, background), _contrast_ratio(accent, surface)) < 3.0:
        errors.append("Accent color must have at least 3:1 contrast against both background and surface.")
    return errors


def current_theme_config() -> dict[str, str]:
    return dict(_CURRENT_CONFIG)


def _mix(first: str, second: str, amount: float) -> str:
    a, b = QColor(first), QColor(second)
    return QColor(
        round(a.red() * (1 - amount) + b.red() * amount),
        round(a.green() * (1 - amount) + b.green() * amount),
        round(a.blue() * (1 - amount) + b.blue() * amount),
    ).name().upper()


def _best_text(backgrounds: tuple[str, ...], preferred: str) -> str:
    candidates = (preferred, "#FFFFFF", "#000000")
    return max(
        candidates,
        key=lambda candidate: min(
            _contrast_ratio(QColor(candidate), QColor(background)) for background in backgrounds
        ),
    )


def _best_semantic_color(candidates: tuple[str, ...], backgrounds: tuple[str, ...], fallback: str) -> str:
    selected = max(
        candidates,
        key=lambda candidate: min(
            _contrast_ratio(QColor(candidate), QColor(background)) for background in backgrounds
        ),
    )
    if min(_contrast_ratio(QColor(selected), QColor(background)) for background in backgrounds) < 4.5:
        return fallback
    return selected


def apply(app: QApplication, config: dict | None = None) -> None:
    global BG, SURFACE, DIM, TODAY_BG, INK, MUTED, FAINT, LINE, LINE_SOFT
    global CONTROL, CONTROL_HOVER, ACCENT, ACCENT_SOFT, ACCENT_INK
    global ACCENT_HOVER, ACCENT_BUTTON_TEXT, NOW, SUCCESS, _CURRENT_CONFIG

    selected = normalize_theme(config)
    _CURRENT_CONFIG = selected
    BG = selected["background"]
    SURFACE = selected["surface"]
    INK = selected["text"]
    ACCENT = selected["accent"]
    background_mix = _mix(BG, SURFACE, 0.5)
    DIM = _mix(BG, SURFACE, 0.5)
    LINE = _mix(background_mix, INK, 0.30)
    LINE_SOFT = _mix(background_mix, INK, 0.12)
    CONTROL = _mix(SURFACE, INK, 0.07)
    CONTROL_HOVER = _mix(SURFACE, INK, 0.15)
    ACCENT_SOFT = _mix(SURFACE, ACCENT, 0.14)
    TODAY_BG = _mix(SURFACE, ACCENT, 0.11)
    text_backgrounds = (BG, SURFACE)
    muted = _mix(INK, background_mix, 0.2)
    MUTED = muted if min(
        _contrast_ratio(QColor(muted), QColor(background)) for background in text_backgrounds
    ) >= 4.5 else INK
    FAINT = MUTED
    ACCENT_INK = _best_text((ACCENT_SOFT,), INK)
    ACCENT_HOVER = _mix(ACCENT, _best_text((ACCENT,), INK), 0.13)
    ACCENT_BUTTON_TEXT = _best_text((ACCENT, ACCENT_HOVER), INK)
    NOW = _best_semantic_color(("#B42318", "#FF847A"), text_backgrounds, INK)
    SUCCESS = _best_semantic_color(("#276B3A", "#78D69B"), text_backgrounds, INK)

    app.setStyle("Fusion")
    app.setFont(QFont(FAMILY, SIZE))
    palette = QPalette()
    normal_colors = {
        QPalette.ColorRole.Window: BG,
        QPalette.ColorRole.WindowText: INK,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: DIM,
        QPalette.ColorRole.ToolTipBase: INK,
        QPalette.ColorRole.ToolTipText: "#FFFFFF",
        QPalette.ColorRole.Text: INK,
        QPalette.ColorRole.Button: CONTROL,
        QPalette.ColorRole.ButtonText: INK,
        QPalette.ColorRole.BrightText: "#FFFFFF",
        QPalette.ColorRole.Highlight: ACCENT_SOFT,
        QPalette.ColorRole.HighlightedText: ACCENT_INK,
        QPalette.ColorRole.Link: ACCENT_INK,
        QPalette.ColorRole.LinkVisited: ACCENT_INK,
        QPalette.ColorRole.Mid: MUTED,
        QPalette.ColorRole.Midlight: LINE_SOFT,
        QPalette.ColorRole.Dark: LINE,
        QPalette.ColorRole.Light: SURFACE,
        QPalette.ColorRole.Shadow: LINE,
        QPalette.ColorRole.PlaceholderText: FAINT,
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color in normal_colors.items():
            palette.setColor(group, role, QColor(color))
    for role, color in normal_colors.items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(FAINT))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QWidget {{ color: {INK}; font-family: "{FAMILY}"; font-size: {SIZE}pt; }}
        QMainWindow, QDialog {{ background: {BG}; }}
        QFrame#sidebar {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
        QScrollArea {{ background: {BG}; border: 0; }}
        QScrollArea::viewport {{ background: {BG}; }}
        QFrame#sidebar QScrollArea, QFrame#sidebar QScrollArea::viewport {{
            background: {SURFACE};
        }}
        QWidget#sidebarBody {{ background: {SURFACE}; }}
        QMenuBar {{ background: {SURFACE}; color: {INK}; }}
        QMenuBar::item {{ background: transparent; padding: 5px 8px; }}
        QMenuBar::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_INK}; }}
        QMenu {{ background: {SURFACE}; color: {INK}; border: 1px solid {LINE}; }}
        QMenu::item {{ padding: 5px 24px 5px 8px; }}
        QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_INK}; }}
        QLabel#brand {{ font-size: 19pt; font-weight: 700; }}
        QLabel#pageTitle {{ font-size: 18pt; font-weight: 700; }}
        QLabel#muted {{ color: {MUTED}; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
        QDateTimeEdit, QComboBox, QListWidget, QTreeWidget, QTableWidget {{
            background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px;
            selection-background-color: {ACCENT_SOFT}; selection-color: {ACCENT_INK};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 2px solid {ACCENT};
        }}
        QPushButton {{
            background: {CONTROL}; border: 1px solid {CONTROL}; border-radius: 6px;
            padding: 7px 13px; min-height: 18px;
        }}
        QPushButton:hover {{ background: {CONTROL_HOVER}; }}
        QPushButton:pressed {{ background: {LINE}; }}
        QPushButton:disabled {{ color: {FAINT}; }}
        QPushButton[primary="true"] {{ color: {ACCENT_BUTTON_TEXT}; background: {ACCENT}; border-color: {ACCENT}; font-weight: 600; }}
        QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; }}
        QPushButton[danger="true"] {{ color: {NOW}; }}
        QPushButton#navItem {{
            text-align: left; background: transparent; border: 0; padding: 8px 12px;
        }}
        QPushButton#navItem:hover, QPushButton#navItem[active="true"] {{
            color: {ACCENT_INK}; background: {ACCENT_SOFT};
        }}
        QTreeWidget::item {{ padding: 6px; }}
        QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: 0; padding: 8px; }}
        QStatusBar {{ color: {MUTED}; }}
        QFrame[card="true"] {{
            background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 10px;
        }}
        QWidget#dashboardArea {{ background: {BG}; }}
        QFrame#dashboardCard {{
            background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 10px;
        }}
        QFrame#dashboardCard > QWidget {{ background: transparent; }}
        QFrame[dropTarget="true"] {{ border: 2px solid {ACCENT}; }}
        QWidget[density="dense"] QPushButton {{ padding: 4px 10px; min-height: 15px; }}
        QWidget[density="dense"] QTreeWidget::item,
        QWidget[density="dense"] QListWidget::item {{ padding: 3px; }}
        QWidget[density="dense"] QFrame#sidebar QPushButton {{ padding: 5px 10px; }}
        QScrollBar:vertical {{ width: 10px; background: {BG}; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QToolTip {{ background: {INK}; color: white; border: 0; padding: 5px; }}
    """)


def font(size: int = SIZE, bold: bool = False) -> QFont:
    result = QFont(FAMILY, size)
    result.setBold(bold)
    return result


def set_density(root: QWidget, density: str) -> None:
    global CURRENT_DENSITY
    CURRENT_DENSITY = density if density in DENSITY_OPTIONS else "comfortable"
    root.setProperty("density", CURRENT_DENSITY)
    root.style().unpolish(root)
    root.style().polish(root)


def center(win: QDialog, parent: QWidget | None = None) -> None:
    win.adjustSize()
    if parent is not None and parent.isVisible():
        target = parent.window().frameGeometry()
        win.move(target.center() - win.rect().center())
    else:
        screen = QApplication.primaryScreen()
        if screen is not None:
            win.move(screen.availableGeometry().center() - win.rect().center())
