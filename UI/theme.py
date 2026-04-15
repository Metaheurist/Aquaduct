"""TikTok-style Qt stylesheet."""

TIKTOK_QSS = """
QWidget { background: #0F0F10; color: #FFFFFF; font-family: "Segoe UI", "Arial"; font-size: 12px; }
QTabWidget::pane { border: 1px solid #23232B; border-radius: 14px; padding: 8px; background: #0B0B0F; }
QTabBar::tab { background: #15151B; color: #B7B7C2; padding: 10px 14px; margin: 6px 6px 0 0;
               border-top-left-radius: 14px; border-top-right-radius: 14px; border: 1px solid #23232B; }
QTabBar::tab:selected { color: #FFFFFF; border-bottom: 3px solid #25F4EE; }
QLineEdit, QTextEdit, QListWidget, QSpinBox, QComboBox {
  background: #15151B; border: 1px solid #2A2A33; border-radius: 12px; padding: 8px; color: #FFFFFF;
}
QLineEdit:focus, QTextEdit:focus, QListWidget:focus, QSpinBox:focus, QComboBox:focus {
  border: 1px solid #25F4EE;
}
QPushButton {
  background: #15151B; border: 1px solid #2A2A33; border-radius: 12px; padding: 10px 12px; color: #FFFFFF;
}
QPushButton:hover { border: 1px solid #25F4EE; }
QPushButton:pressed { border: 1px solid #FE2C55; }
QPushButton#primary { background: #25F4EE; color: #0B0B0F; border: 1px solid #25F4EE; font-weight: 600; }
QPushButton#danger { background: #FE2C55; color: #FFFFFF; border: 1px solid #FE2C55; font-weight: 600; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 1px solid #2A2A33; background: #15151B; }
QCheckBox::indicator:checked { background: #25F4EE; border: 1px solid #25F4EE; }
"""
