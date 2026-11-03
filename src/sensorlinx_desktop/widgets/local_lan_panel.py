"""Local LAN Direct Stream Monitor & XTEA ECB Decryptor UI Panel."""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..local_probe import FrameTypeState, LocalHostState, LocalLanManager


class LocalLanPanel(QWidget):
    """GUI panel for direct LAN XTEA decryption & monitoring of HBX controllers on TCP port 2000."""

    def __init__(self, manager: LocalLanManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self._selected_host: str = self.manager.hosts[0] if self.manager.hosts else "192.168.1.50"
        self._selected_frame_key: str = ""

        self._build_ui()
        self.manager.state_updated.connect(self.refresh_ui)
        self.refresh_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Header & Controls
        hdr_frame = QFrame()
        hdr_frame.setObjectName("CardFrame")
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(16, 12, 16, 12)

        title_col = QVBoxLayout()
        title_lbl = QLabel("Local LAN Direct Stream Monitor & XTEA Decryptor (TCP Port 2000)")
        title_lbl.setObjectName("SectionHeader")
        sub_lbl = QLabel(
            "Direct zero-cloud connection to local HBX controllers on TCP port 2000 (ECO-0600 & ZON-0600)  •  "
            "Real-time 32-round little-endian XTEA ECB decryption (Key loaded from ~/.sensorlinx_xtea.key)"
        )
        sub_lbl.setObjectName("MutedText")
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        hdr_lay.addLayout(title_col, 1)

        self.add_ip_edit = QLineEdit()
        self.add_ip_edit.setPlaceholderText("Add local IP (e.g. 192.168.1.52)")
        self.add_ip_edit.setMaximumWidth(190)
        hdr_lay.addWidget(self.add_ip_edit)

        add_btn = QPushButton("+ Add IP")
        add_btn.clicked.connect(self._on_add_ip)
        hdr_lay.addWidget(add_btn)

        self.toggle_btn = QPushButton("▶ Start Local Stream")
        self.toggle_btn.setObjectName("PrimaryButton")
        self.toggle_btn.clicked.connect(self._on_toggle_stream)
        hdr_lay.addWidget(self.toggle_btn)

        root.addWidget(hdr_frame)

        # Host Summary Cards row
        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(10)
        root.addLayout(self.cards_grid)

        # Selector Bar + Live Decrypted Frame Banner
        sel_frame = QFrame()
        sel_frame.setObjectName("CardFrame")
        sel_outer = QVBoxLayout(sel_frame)
        sel_outer.setContentsMargins(14, 8, 14, 8)
        sel_outer.setSpacing(6)

        sel_lay = QHBoxLayout()
        sel_lay.addWidget(QLabel("Inspect Device:"))
        self.host_combo = QComboBox()
        self.host_combo.addItems(self.manager.hosts)
        self.host_combo.currentTextChanged.connect(self._on_host_selected)
        sel_lay.addWidget(self.host_combo)

        sel_lay.addSpacing(16)
        sel_lay.addWidget(QLabel("Frame Stream:"))
        self.frame_combo = QComboBox()
        self.frame_combo.setMinimumWidth(220)
        self.frame_combo.currentTextChanged.connect(self._on_frame_selected)
        sel_lay.addWidget(self.frame_combo)

        sel_lay.addStretch()
        self.stream_stats_lbl = QLabel("Waiting for frames...")
        self.stream_stats_lbl.setObjectName("MutedText")
        sel_lay.addWidget(self.stream_stats_lbl)
        sel_outer.addLayout(sel_lay)

        self.decrypted_banner = QLineEdit()
        self.decrypted_banner.setReadOnly(True)
        self.decrypted_banner.setFont(QFont("Consolas", 10))
        self.decrypted_banner.setPlaceholderText(
            "Decrypted XTEA plaintext frame will appear here (e.g. {type:primaryinfo,data:{priCPU:AECO-0001,...}})"
        )
        sel_outer.addWidget(self.decrypted_banner)

        root.addWidget(sel_frame)

        # Main Splitter: Left = 8-byte XTEA Block Table, Right = Live Change Log & Protocol Notes
        splitter = QSplitter(Qt.Orientation.Horizontal)

        block_group = QGroupBox("Live 8-Byte (64-Bit) XTEA ECB Block Register Map")
        bg_lay = QVBoxLayout(block_group)
        self.block_table = QTableWidget(0, 6)
        self.block_table.setHorizontalHeaderLabels([
            "Block #",
            "Byte Offset",
            "Decrypted Plaintext (ASCII)",
            "Current Ciphertext (Hex)",
            "Changes",
            "Structure / Role (Editable Note)",
        ])
        self.block_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.block_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.block_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.block_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.block_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.block_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.block_table.setAlternatingRowColors(True)
        bg_lay.addWidget(self.block_table)
        splitter.addWidget(block_group)

        right_col = QWidget()
        rc_lay = QVBoxLayout(right_col)
        rc_lay.setContentsMargins(0, 0, 0, 0)
        rc_lay.setSpacing(10)

        events_group = QGroupBox("Live Decrypted Block Change Feed (Real-Time State Transitions)")
        eg_lay = QVBoxLayout(events_group)
        self.events_list = QListWidget()
        eg_lay.addWidget(self.events_list)
        rc_lay.addWidget(events_group, 1)

        corr_group = QGroupBox("Cloud ↔ Local XTEA Block Correlator")
        cg_lay = QVBoxLayout(corr_group)
        self.corr_list = QListWidget()
        cg_lay.addWidget(self.corr_list)
        rc_lay.addWidget(corr_group, 1)

        notes_group = QGroupBox("Local Hardware XTEA Protocol Summary")
        ng_lay = QVBoxLayout(notes_group)
        notes_lbl = QLabel(
            "• <b>Cipher & Key</b>: 32-round little-endian <b>XTEA ECB</b> with a 128-bit key loaded locally from "
            "<code>~/.sensorlinx_xtea.key</code> or <code>HBX_XTEA_KEY</code> (not stored in repository).<br>"
            "• <b>ECO-0600</b> (e.g. <code>AECO-0001</code>): Broadcasts <code>{type:primaryinfo,...}</code> "
            "(168B) with live stage status (<code>stgS</code>), backup state (<code>useBkUp/priBUp</code>), pump state "
            "(<code>secPmp</code>), and outdoor temp (<code>out</code>).<br>"
            "• <b>ZON-0600</b> (e.g. <code>AZON-0001</code>): Broadcasts <code>{type:primaryinfo,...}</code> "
            "(128B) with priority zone (<code>znInPri</code>), active zone demand (<code>znInDem</code>), and outdoor temp."
        )
        notes_lbl.setWordWrap(True)
        ng_lay.addWidget(notes_lbl)
        rc_lay.addWidget(notes_group, 1)

        splitter.addWidget(right_col)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _on_add_ip(self) -> None:
        ip = self.add_ip_edit.text().strip()
        if not ip:
            return
        self.manager.add_host(ip)
        if self.host_combo.findText(ip) < 0:
            self.host_combo.addItem(ip)
        self.add_ip_edit.clear()

    def _on_toggle_stream(self) -> None:
        if self.manager.is_running:
            asyncio.ensure_future(self.manager.stop())
        else:
            asyncio.ensure_future(self.manager.start())

    def _on_host_selected(self, host: str) -> None:
        if not host:
            return
        self._selected_host = host
        self._selected_frame_key = ""
        self.refresh_ui()

    def _on_frame_selected(self, fkey: str) -> None:
        if not fkey:
            return
        self._selected_frame_key = fkey
        self._populate_block_table()

    def refresh_ui(self) -> None:
        if self.manager.is_running:
            self.toggle_btn.setText("⏹ Stop Local Stream")
        else:
            self.toggle_btn.setText("▶ Start Local Stream")

        # Rebuild top host cards
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for col, host in enumerate(self.manager.hosts):
            st = self.manager.states.get(host)
            if not st:
                continue
            card = self._build_host_card(st)
            self.cards_grid.addWidget(card, 0, col)

        # Update frame combo for selected host
        st = self.manager.states.get(self._selected_host)
        if st:
            fkeys = sorted(st.frame_types.keys())
            existing = [self.frame_combo.itemText(i) for i in range(self.frame_combo.count())]
            if fkeys != existing:
                self.frame_combo.blockSignals(True)
                self.frame_combo.clear()
                self.frame_combo.addItems(fkeys)
                if self._selected_frame_key in fkeys:
                    self.frame_combo.setCurrentText(self._selected_frame_key)
                elif fkeys:
                    self._selected_frame_key = fkeys[0]
                    self.frame_combo.setCurrentIndex(0)
                self.frame_combo.blockSignals(False)
            elif not self._selected_frame_key and fkeys:
                self._selected_frame_key = fkeys[0]

            # Update events list
            self.events_list.clear()
            for evt in st.recent_events[:30]:
                self.events_list.addItem(evt)

        self.corr_list.clear()
        if self.manager.cloud_correlations:
            for c_evt in self.manager.cloud_correlations[:30]:
                self.corr_list.addItem(c_evt)
        else:
            self.corr_list.addItem(
                "Local frames are decrypted directly using your local ~/.sensorlinx_xtea.key."
            )

        self._populate_block_table()

    def _build_host_card(self, st: LocalHostState) -> QFrame:
        card = QFrame()
        card.setObjectName("CardFrame")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        fqdn_part = f" ({st.hostname})" if st.hostname else ""
        hdr = QLabel(f"DEVICE {st.host}:{st.port}{fqdn_part}")
        hdr.setObjectName("CardTitle")
        lay.addWidget(hdr)

        status_lbl = QLabel("● STREAMING & DECRYPTED LIVE" if st.connected else "○ DISCONNECTED")
        status_lbl.setStyleSheet(
            "color: #34D399; font-weight: 700; font-size: 14px;"
            if st.connected
            else "color: #F87171; font-weight: 700; font-size: 14px;"
        )
        lay.addWidget(status_lbl)

        role_lbl = QLabel(st.inferred_device_role())
        role_lbl.setStyleSheet("color: #E2E8F0; font-weight: 600;")
        role_lbl.setWordWrap(True)
        lay.addWidget(role_lbl)

        ft_summary = ", ".join(
            f"{ft.frame_key} ({ft.frame_count} pkts, ~{ft.interval_sec:.1f}s)"
            for ft in st.frame_types.values()
        ) or (st.last_error or "No frames captured yet")
        sub_lbl = QLabel(f"Bytes: {st.bytes_received:,}  •  Frames: {st.frames_received}  •  {ft_summary}")
        sub_lbl.setObjectName("MutedText")
        sub_lbl.setWordWrap(True)
        lay.addWidget(sub_lbl)
        return card

    def _populate_block_table(self) -> None:
        st = self.manager.states.get(self._selected_host)
        if not st or not self._selected_frame_key or self._selected_frame_key not in st.frame_types:
            self.block_table.setRowCount(0)
            self.decrypted_banner.clear()
            self.stream_stats_lbl.setText("Connect to port 2000 stream to view live decrypted 8-byte XTEA blocks.")
            return

        ft: FrameTypeState = st.frame_types[self._selected_frame_key]
        self.stream_stats_lbl.setText(
            f"Frame: {ft.frame_key}  |  Delimiter: {ft.delimiter}  |  Length: {ft.byte_length} bytes ({len(ft.blocks)} × 8B blocks)  |  "
            f"Captured: {ft.frame_count} frames  |  Avg Interval: {ft.interval_sec:.2f}s"
        )
        self.decrypted_banner.setText(ft.last_decrypted_text)

        mono_font = QFont("Consolas", 10)
        now = time.time()
        self.block_table.setRowCount(len(ft.blocks))
        for row, blk in enumerate(ft.blocks):
            recently_changed = blk.last_changed_ts is not None and (now - blk.last_changed_ts) < 10.0
            bg_color = QColor("#431407") if recently_changed else (QColor("#1E293B") if blk.change_count > 0 else None)

            items = [
                QTableWidgetItem(f"Block {blk.index:02d}"),
                QTableWidgetItem(f"+{blk.index * 8:03d}..{blk.index * 8 + 7:03d}"),
                QTableWidgetItem(blk.current_ascii),
                QTableWidgetItem(blk.current_hex),
                QTableWidgetItem(str(blk.change_count)),
                QTableWidgetItem(blk.annotation),
            ]
            items[2].setFont(mono_font)
            items[3].setFont(mono_font)
            for col_idx, it in enumerate(items):
                if col_idx < 5:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bg_color is not None:
                    it.setBackground(bg_color)
                if recently_changed and col_idx in (2, 3):
                    it.setForeground(QColor("#FDBA74"))
                elif col_idx == 2:
                    it.setForeground(QColor("#38BDF8"))
                self.block_table.setItem(row, col_idx, it)
