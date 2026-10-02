"""A single, neutral-plus-accent stylesheet applied app-wide for a
professional, non-cluttered look (no theming system in Phase-1)."""
from app.ui.resources import resource_path

ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
BG = "#f7f8fa"
SURFACE = "#ffffff"
BORDER = "#d8dce1"
TEXT = "#1f2430"
MUTED = "#6b7280"
INDICATOR_BORDER = "#8b93a1"
# Forward slashes + quotes so the url() works on Windows and in paths with spaces.
CHECK_ICON = resource_path("app", "ui", "assets", "check.svg").as_posix()

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {BG};
}}

QLabel#screenTitle {{
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 4px;
}}

QLabel#statusBar {{
    color: {MUTED};
    padding: 4px 2px;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {SURFACE};
    border-radius: 6px;
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: {MUTED};
}}

QTabBar::tab:selected {{
    background: {SURFACE};
    color: {TEXT};
    font-weight: 600;
    border: 1px solid {BORDER};
    border-bottom: none;
}}

QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT};
}}

QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}

QPushButton:pressed {{
    background: #eef1f5;
}}

QPushButton:disabled {{
    color: #a3a9b3;
}}

QPushButton#primaryButton {{
    background: {ACCENT};
    color: white;
    border: none;
    font-weight: 600;
    padding: 9px 18px;
}}

QPushButton#primaryButton:hover {{
    background: {ACCENT_DARK};
}}

QLineEdit, QComboBox, QDateEdit, QListWidget, QTableWidget, QTextEdit, QTextBrowser {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 6px;
}}

/* Once QComboBox is styled at all, macOS sizes its popup list to the
   combo's text area minus the check-mark column, so short items like
   "2025" got clipped to "202". Give both a sensible floor. */
QComboBox {{
    min-width: 72px;
}}

QComboBox QAbstractItemView {{
    min-width: 110px;
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 24px;
    padding: 0 8px;
}}

QTableWidget {{
    gridline-color: {BORDER};
    selection-background-color: #dbe6fd;
    selection-color: {TEXT};
}}

QHeaderView::section {{
    background: #eef1f5;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: 600;
    color: {MUTED};
}}

QCheckBox, QRadioButton {{
    spacing: 8px;
    background: transparent;
}}

/* Indicators are drawn explicitly: with the app-wide QWidget background
   above, macOS's native style otherwise paints checkbox/radio indicators
   invisibly (white on white), leaving just the label. */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {INDICATOR_BORDER};
    background: {SURFACE};
}}

QCheckBox::indicator {{
    border-radius: 4px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("{CHECK_ICON}");
}}

QRadioButton::indicator:checked {{
    border-color: {ACCENT};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {ACCENT}, stop:0.45 {ACCENT}, stop:0.55 {SURFACE}, stop:1 {SURFACE});
}}

QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {BORDER};
    background: #eef1f5;
}}

QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 5px;
    background: {SURFACE};
    text-align: center;
    height: 18px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}

QScrollArea {{
    border: none;
}}

QFrame#emptyState {{
    background: {SURFACE};
    border: 1px dashed {BORDER};
    border-radius: 10px;
    padding: 40px;
}}

QFrame#moreFilters {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px;
}}
"""
