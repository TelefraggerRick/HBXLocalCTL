"""Connection mode selector (Local LAN, Cloud Login, or Demo Mode) for SensorLinx Desktop."""
from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LoginDialog(QDialog):
    """Modal dialog to choose Local LAN Mode (no cloud), Demo Mode, or HBX Cloud Login."""

    def __init__(
        self,
        initial_email: str = "",
        initial_password: str = "",
        remember: bool = False,
        error_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection Mode • HBX SensorLinx Desktop")
        self.setMinimumWidth(480)
        self.selected_mode: str = "local"
        self.use_demo_mode: bool = False
        self.use_local_mode: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("HBX Controls • Connection Mode")
        title.setObjectName("SectionHeader")
        layout.addWidget(title)

        sub = QLabel(
            "Connect directly to your local HBX controllers on your LAN (on TCP port 2000 "
            "using XTEA decryption — no cloud required), run Demo Simulation Mode, or sign in to mobile.sensorlinx.co."
        )
        sub.setWordWrap(True)
        sub.setObjectName("MutedText")
        layout.addWidget(sub)

        if error_text:
            err_lbl = QLabel(error_text)
            err_lbl.setWordWrap(True)
            err_lbl.setStyleSheet("color: #F87171; font-weight: 600;")
            layout.addWidget(err_lbl)

        # Direct Local LAN Card
        local_frame = QFrame()
        local_frame.setObjectName("CardFrame")
        local_lay = QVBoxLayout(local_frame)
        local_lay.setContentsMargins(16, 14, 16, 14)
        local_lay.setSpacing(8)
        local_hdr = QLabel("📡 Direct Local LAN Mode (Zero Cloud Dependency)")
        local_hdr.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 14px;")
        local_desc = QLabel(
            "Streams and XTEA-decrypts live telemetry directly from your local controllers "
            "(ECO-0600 and ZON-0600 on TCP port 2000) on your local network."
        )
        local_desc.setWordWrap(True)
        local_desc.setObjectName("MutedText")
        self.local_btn = QPushButton("▶ Use Local LAN Mode (No Cloud)")
        self.local_btn.setObjectName("PrimaryButton")
        self.local_btn.clicked.connect(self._on_local_clicked)
        local_lay.addWidget(local_hdr)
        local_lay.addWidget(local_desc)
        local_lay.addWidget(self.local_btn)
        layout.addWidget(local_frame)

        # Optional Cloud Account Card
        form_frame = QFrame()
        form_frame.setObjectName("CardFrame")
        form = QFormLayout(form_frame)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)

        self.email_edit = QLineEdit(initial_email)
        self.email_edit.setPlaceholderText("you@example.com (Only needed for Cloud Mode)")
        form.addRow("Cloud Email:", self.email_edit)

        self.password_edit = QLineEdit(initial_password)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Your SensorLinx cloud password")
        form.addRow("Password:", self.password_edit)

        self.remember_chk = QCheckBox("Remember cloud credentials on this computer")
        self.remember_chk.setChecked(remember)
        form.addRow("", self.remember_chk)

        layout.addWidget(form_frame)

        btn_row = QHBoxLayout()
        self.demo_btn = QPushButton("Launch Demo / Simulation Mode")
        self.demo_btn.clicked.connect(self._on_demo_clicked)
        btn_row.addWidget(self.demo_btn)

        self.login_btn = QPushButton("Sign In to Cloud")
        self.login_btn.clicked.connect(self._on_login_clicked)
        btn_row.addWidget(self.login_btn)

        layout.addLayout(btn_row)

    def _on_local_clicked(self) -> None:
        self.selected_mode = "local"
        self.use_local_mode = True
        self.use_demo_mode = False
        self.accept()

    def _on_demo_clicked(self) -> None:
        self.selected_mode = "demo"
        self.use_demo_mode = True
        self.use_local_mode = False
        self.accept()

    def _on_login_clicked(self) -> None:
        self.selected_mode = "cloud"
        self.use_demo_mode = False
        self.use_local_mode = False
        self.accept()

    @property
    def email(self) -> str:
        return self.email_edit.text().strip()

    @property
    def password(self) -> str:
        return self.password_edit.text()

    @property
    def remember(self) -> bool:
        return self.remember_chk.isChecked()
