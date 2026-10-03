from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class StatusCard(QFrame):
    """Rounded card widget displaying a label and value."""

    def __init__(self, icon: str, label: str, value: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("statusCard")

        layout = QVBoxLayout(self)

        self.lbl_title = QLabel(f"{icon} {label}")
        self.lbl_title.setStyleSheet("color: #a6adc8; font-size: 12px;")

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(
            "color: #cdd6f4; font-size: 16px; font-weight: bold;"
        )
        self.lbl_value.setWordWrap(True)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addStretch()

        self.set_highlight("#45475a")

    def set_value(self, value: str):
        self.lbl_value.setText(value)

    def set_highlight(self, color: str):
        self.setStyleSheet(f"""
            QFrame#statusCard {{
                background-color: #313244;
                border-radius: 8px;
                border-left: 3px solid {color};
            }}
        """)
