"""Direct Local LAN TCP port 2000 stream monitor and XTEA ECB decryptor for HBX 0600 devices."""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal


DEFAULT_LOCAL_PORT: int = 2000
DEFAULT_CODEBOOK_PATH: Path = Path.home() / ".sensorlinx_ecb_codebook.json"
DEFAULT_KEY_FILE_PATH: Path = Path.home() / ".sensorlinx_xtea.key"
DEFAULT_HOSTS_PATH: Path = Path.home() / ".sensorlinx_hosts.json"


def _load_local_hosts() -> List[str]:
    """Load local HBX controller IP addresses from environment, local file, or generic defaults."""
    env_hosts = os.environ.get("HBX_LOCAL_HOSTS", "").strip()
    if env_hosts:
        return [h.strip() for h in env_hosts.split(",") if h.strip()]
    for candidate in (DEFAULT_HOSTS_PATH, Path(".sensorlinx_hosts.json")):
        try:
            if candidate.exists():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return [str(h).strip() for h in data if str(h).strip()]
        except Exception:
            pass
    return ["192.168.1.50", "192.168.1.51"]


DEFAULT_LOCAL_HOSTS: List[str] = _load_local_hosts()


def _load_local_xtea_key() -> bytes:
    """Load the 16-byte XTEA key from environment or local key file (`~/.sensorlinx_xtea.key`).

    The hardware key is intentionally omitted from the public repository for security.
    """
    env_key = os.environ.get("HBX_XTEA_KEY", "").strip()
    if len(env_key) == 16:
        return env_key.encode("latin1")
    for candidate in (DEFAULT_KEY_FILE_PATH, Path(".sensorlinx_xtea.key")):
        try:
            if candidate.exists():
                raw = candidate.read_bytes().strip(b"\r\n")
                if len(raw) == 16:
                    return raw
        except Exception:
            pass
    # Placeholder fallback for automated tests / unconfigured environments
    return b"0123456789ABCDEF"


HBX_XTEA_KEY_ASCII: bytes = _load_local_xtea_key()
HBX_XTEA_KEY: Tuple[int, int, int, int] = struct.unpack("<4I", HBX_XTEA_KEY_ASCII)
XTEA_DELTA: int = 2654435769  # 0x9E3779B9
XTEA_INIT_SUM: int = 3337565984  # 0xC6EF3720 == (XTEA_DELTA * 32) & 0xFFFFFFFF


def xtea_decrypt_block(block: bytes, key: Tuple[int, int, int, int] = HBX_XTEA_KEY) -> bytes:
    """Decrypt a single 8-byte (64-bit) little-endian XTEA ECB block (32 rounds)."""
    if len(block) < 8:
        block = block.ljust(8, b"\x00")
    v0, v1 = struct.unpack("<2I", block[:8])
    sum_val = XTEA_INIT_SUM
    for _ in range(32):
        v1 = (
            v1
            - ((((v0 << 4) & 0xFFFFFFFF) ^ (v0 >> 5)) + v0 ^ (sum_val + key[(sum_val >> 11) & 3]))
        ) & 0xFFFFFFFF
        sum_val = (sum_val - XTEA_DELTA) & 0xFFFFFFFF
        v0 = (
            v0
            - ((((v1 << 4) & 0xFFFFFFFF) ^ (v1 >> 5)) + v1 ^ (sum_val + key[sum_val & 3]))
        ) & 0xFFFFFFFF
    return struct.pack("<2I", v0, v1)


def xtea_encrypt_block(block: bytes, key: Tuple[int, int, int, int] = HBX_XTEA_KEY) -> bytes:
    """Encrypt a single 8-byte (64-bit) little-endian XTEA ECB block (32 rounds)."""
    if len(block) < 8:
        block = block.ljust(8, b" ")
    v0, v1 = struct.unpack("<2I", block[:8])
    sum_val = 0
    for _ in range(32):
        v0 = (
            v0
            + ((((v1 << 4) & 0xFFFFFFFF) ^ (v1 >> 5)) + v1 ^ (sum_val + key[sum_val & 3]))
        ) & 0xFFFFFFFF
        sum_val = (sum_val + XTEA_DELTA) & 0xFFFFFFFF
        v1 = (
            v1
            + ((((v0 << 4) & 0xFFFFFFFF) ^ (v0 >> 5)) + v0 ^ (sum_val + key[(sum_val >> 11) & 3]))
        ) & 0xFFFFFFFF
    return struct.pack("<2I", v0, v1)


def xtea_decrypt(data: bytes, key: Tuple[int, int, int, int] = HBX_XTEA_KEY) -> bytes:
    """Decrypt a multi-block XTEA ECB payload."""
    out = bytearray()
    n = (len(data) // 8) * 8
    for i in range(0, n, 8):
        out.extend(xtea_decrypt_block(data[i : i + 8], key))
    return bytes(out)


def xtea_encrypt(data: bytes, key: Tuple[int, int, int, int] = HBX_XTEA_KEY, pad_byte: bytes = b" ") -> bytes:
    """Encrypt a payload using HBX 32-round little-endian XTEA ECB."""
    rem = len(data) % 8
    if rem:
        data = data + pad_byte * (8 - rem)
    out = bytearray()
    for i in range(0, len(data), 8):
        out.extend(xtea_encrypt_block(data[i : i + 8], key))
    return bytes(out)


def parse_hbx_pseudo_json(text: str) -> Dict[str, Any]:
    """Parse HBX unquoted pseudo-JSON frame strings into a structured dictionary.

    Example input:
      '{type:primaryinfo,data:{priCPU:AECO-0001,stgS:1,numStg:1,out:37.00,version:2.08,crc:41603}}'
      '{type:OK,syncCode:AZON-0001,data:{tz:-3.5,hrs:11,mins:9,secs:6,dow:1,days:2,month:10,year:2026,out:37,crc:11}}'
    """
    cleaned = text.strip(" \r\n\t\x00")
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        return {}
    result: Dict[str, Any] = {"raw": cleaned}

    m_type = re.search(r"\btype:([^,}]+)", cleaned)
    if m_type:
        result["type"] = m_type.group(1).strip()

    m_sync = re.search(r"\bsyncCode:([^,}]+)", cleaned)
    if m_sync:
        result["syncCode"] = m_sync.group(1).strip()

    m_data = re.search(r"\bdata:\{([^}]*)\}", cleaned)
    data_dict: Dict[str, Any] = {}
    if m_data:
        inner = m_data.group(1)
        for pair in inner.split(","):
            if ":" not in pair:
                continue
            k, v = pair.split(":", 1)
            k = k.strip()
            v = v.strip()
            # Convert numeric values where appropriate (keep PASS and version as strings if needed)
            if k not in ("PASS", "SSID", "version", "thmBVer", "priCPU", "syncCode"):
                try:
                    if "." in v:
                        data_dict[k] = float(v)
                    else:
                        data_dict[k] = int(v)
                    continue
                except ValueError:
                    pass
            elif k == "out":
                try:
                    data_dict[k] = float(v)
                    continue
                except ValueError:
                    pass
            data_dict[k] = v
    result["data"] = data_dict
    return result


@dataclass
class BlockSlotState:
    """Tracks the current and historical 8-byte XTEA ECB blocks and decrypted ASCII at an 8-byte offset."""

    index: int
    current_hex: str
    current_ascii: str = ""
    previous_hex: Optional[str] = None
    previous_ascii: Optional[str] = None
    change_count: int = 0
    last_changed_ts: Optional[float] = None
    seen_values: List[str] = field(default_factory=list)
    annotation: str = ""


@dataclass
class FrameTypeState:
    """State of a specific frame type (e.g., 'A_168B', 'A_128B', 'B_120B') on a host."""

    frame_key: str
    delimiter: str
    byte_length: int
    frame_count: int = 0
    last_received_ts: float = 0.0
    interval_sec: float = 0.0
    last_decrypted_text: str = ""
    last_parsed: Dict[str, Any] = field(default_factory=dict)
    blocks: List[BlockSlotState] = field(default_factory=list)


@dataclass
class LocalHostState:
    """Aggregated state for a single local HBX controller IP (e.g., 192.168.1.50)."""

    host: str
    port: int = DEFAULT_LOCAL_PORT
    hostname: str = ""
    connected: bool = False
    bytes_received: int = 0
    frames_received: int = 0
    last_seen_ts: Optional[float] = None
    last_error: str = ""
    frame_types: Dict[str, FrameTypeState] = field(default_factory=dict)
    recent_events: List[str] = field(default_factory=list)
    decoded_telemetry: Dict[str, Any] = field(default_factory=dict)

    def inferred_device_role(self) -> str:
        """Return the decoded HBX device identity and live summary if decrypted frames are available."""
        tel = self.decoded_telemetry
        sync_code = tel.get("syncCode") or tel.get("priCPU") or ""
        fw = tel.get("version") or ""
        out_f = tel.get("out")
        out_str = ""
        if out_f is not None:
            try:
                f_val = float(out_f)
                c_val = (f_val - 32.0) * 5.0 / 9.0
                out_str = f"  •  Outdoor: {f_val:.1f} °F ({c_val:.1f} °C)"
            except (ValueError, TypeError):
                out_str = f"  •  Outdoor: {out_f}"

        if "stgS" in tel or sync_code.startswith("AECO"):
            stg = "ON" if tel.get("stgS") else "OFF"
            bk = "ON" if tel.get("priBUp") else ("Armed" if tel.get("useBkUp") else "OFF")
            pmp = tel.get("secPmp", "—")
            return (
                f"ECO-0600 ({sync_code or 'Primary'}, FW v{fw})  •  "
                f"Stage 1: {stg}  •  Backup: {bk}  •  SecPmp: {pmp}{out_str}"
            )
        if "znInPri" in tel or sync_code.startswith("AZON"):
            z_pri = tel.get("znInPri", "—")
            z_dem = tel.get("znInDem", 0)
            return (
                f"ZON-0600 ({sync_code or 'Zone Controller'}, FW v{fw})  •  "
                f"Priority Zone: {z_pri}  •  Demand Mask: {z_dem}{out_str}"
            )
        if "A_168B" in self.frame_types:
            return "HBX ECO-0600 Controller (21-block / 168B XTEA Frame, ~1.6s cycle)"
        if "A_128B" in self.frame_types:
            return "HBX ZON-0600 Controller (16-block / 128B XTEA Frame, ~7.0s cycle)"
        if self.connected:
            return "HBX Espressif Wi-Fi Bridge (Connected on TCP :2000)"
        return "Offline / Connecting..."


def parse_delimited_frames(buffer: bytearray, flush_trailing: bool = True) -> List[Tuple[bytes, str]]:
    """Extract complete `<<<>>>` and `<<<` delimited binary frames from a raw TCP byte buffer.

    Strips any leading `>` bytes left over when `<<<>>>` was split across TCP reads so 8-byte
    XTEA block alignment is always preserved.
    """
    extracted: List[Tuple[bytes, str]] = []
    while True:
        idx = buffer.find(b"<<<")
        if idx < 0:
            break
        if idx + 3 == len(buffer) and not flush_trailing:
            break
        if buffer[idx + 3 : idx + 6] == b">>>":
            payload = bytes(buffer[:idx]).lstrip(b">")
            del buffer[: idx + 6]
            if payload:
                extracted.append((payload, "<<<>>>"))
        else:
            tail = bytes(buffer[idx + 3 :])
            if tail in (b">", b">>") and not flush_trailing:
                break
            payload = bytes(buffer[:idx]).lstrip(b">")
            del buffer[: idx + 3]
            if payload:
                extracted.append((payload, "<<<"))
    return extracted


class LocalLanManager(QObject):
    """Manages persistent async TCP connections to local HBX devices on port 2000 with XTEA decryption."""

    state_updated = Signal()
    block_changed = Signal(str, str, int, str, str)  # host, frame_key, block_idx, old_hex, new_hex

    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        port: int = DEFAULT_LOCAL_PORT,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.hosts: List[str] = list(hosts or DEFAULT_LOCAL_HOSTS)
        self.port: int = port
        self.states: Dict[str, LocalHostState] = {
            h: LocalHostState(host=h, port=port) for h in self.hosts
        }
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running: bool = False
        self.cloud_correlations: List[str] = []
        self._last_cloud_raw: Dict[str, Dict[str, Any]] = {}
        self._recent_block_changes: List[Tuple[float, str, str, int, str, str]] = []
        self.codebook_path: Path = DEFAULT_CODEBOOK_PATH
        self.codebook: Dict[str, Dict[str, Any]] = self._load_codebook()

    def _load_codebook(self) -> Dict[str, Dict[str, Any]]:
        if self.codebook_path.exists():
            try:
                return json.loads(self.codebook_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_codebook(self) -> None:
        try:
            self.codebook_path.write_text(
                json.dumps(self.codebook, indent=2, sort_keys=True), encoding="utf-8"
            )
        except Exception:
            pass

    def on_cloud_data_updated(self, data: Dict[str, Any]) -> None:
        """Compare incoming cloud device states with recent local 8-byte XTEA block changes."""
        if not data or data.get("is_demo"):
            return
        devices = data.get("devices") or {}
        now = time.time()
        ignore_keys = {
            "parameters", "temps", "temperatures", "stages", "backup", "wsd",
            "demands", "pumps", "relays", "changeover", "awayMode", "fanModes",
            "appButton", "auxSetpoint", "connectedAt", "updatedAt",
        }

        cloud_diffs: List[str] = []
        for dev_id, dev in devices.items():
            raw_snap = {
                k: v for k, v in dev.items() if k not in ignore_keys and isinstance(v, (int, float, str, bool))
            }
            params = dev.get("parameters") or {}
            for pk in (
                "temperature_outdoor", "temperature_tank", "target_temperature_tank",
                "temperature_room", "temperature_floor", "humidity", "relays",
            ):
                if pk in params:
                    raw_snap[pk] = params[pk]

            prev = self._last_cloud_raw.get(dev_id)
            if prev is not None:
                for k, v in raw_snap.items():
                    if prev.get(k) != v:
                        cloud_diffs.append(f"{dev_id}.{k}: {prev.get(k)} -> {v}")
            self._last_cloud_raw[dev_id] = raw_snap

        if cloud_diffs:
            recent_local = [
                (ts, h, fk, bidx, old_h, new_h)
                for (ts, h, fk, bidx, old_h, new_h) in self._recent_block_changes
                if now - ts <= 45.0
            ]
            ts_str = time.strftime("%H:%M:%S", time.localtime(now))
            diff_summary = ", ".join(cloud_diffs)
            if recent_local:
                for _, h, fk, bidx, _old_h, new_h in recent_local:
                    key = f"{h}:{fk}:block_{bidx:02d}"
                    entry = self.codebook.setdefault(key, {"observations": {}})
                    entry["observations"][new_h] = {
                        "cloud_diff": diff_summary,
                        "timestamp": ts_str,
                    }
                self.save_codebook()
                loc_summary = ", ".join(f"{h} {fk}[#{bidx:02d}]={new_h}" for _, h, fk, bidx, _, new_h in recent_local)
                msg = f"[{ts_str}] MATCH: Cloud ({diff_summary}) <=> Local ({loc_summary})"
            else:
                msg = f"[{ts_str}] Cloud changed ({diff_summary}) — watching local blocks..."

            self.cloud_correlations.insert(0, msg)
            if len(self.cloud_correlations) > 50:
                self.cloud_correlations.pop()
            self.state_updated.emit()

    @property
    def is_running(self) -> bool:
        return self._running

    def add_host(self, host: str) -> None:
        host = host.strip()
        if not host:
            return
        if host not in self.states:
            self.states[host] = LocalHostState(host=host, port=self.port)
            self.hosts.append(host)
            if self._running:
                self._tasks[host] = asyncio.ensure_future(self._monitor_host_loop(host))
            self.state_updated.emit()

    async def start(self) -> None:
        """Start background TCP stream listeners for all configured local hosts."""
        if self._running:
            return
        self._running = True
        for host in self.hosts:
            if host not in self._tasks or self._tasks[host].done():
                self._tasks[host] = asyncio.ensure_future(self._monitor_host_loop(host))
        self.state_updated.emit()

    async def stop(self) -> None:
        """Stop all active local TCP listeners."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        for st in self.states.values():
            st.connected = False
        self.state_updated.emit()

    def ingest_frame(self, host: str, payload: bytes, delimiter: str, now: Optional[float] = None) -> None:
        """Decrypt a single extracted frame with XTEA and update 8-byte block & telemetry states."""
        if now is None:
            now = time.time()
        st = self.states.setdefault(host, LocalHostState(host=host, port=self.port))
        st.frames_received += 1
        st.last_seen_ts = now

        # Decrypt the full frame with the locally configured 128-bit XTEA key
        decrypted_bytes = xtea_decrypt(payload)
        decrypted_text = decrypted_bytes.decode("latin1", errors="replace").strip(" \r\n\x00")
        parsed = parse_hbx_pseudo_json(decrypted_text)

        # Distinguish frame types by parsed type or byte length
        pkt_type = parsed.get("type", "")
        prefix = "A" if (delimiter == "<<<>>>" or pkt_type == "primaryinfo") else "B"
        frame_key = f"{prefix}_{len(payload)}B"
        ft = st.frame_types.get(frame_key)
        if ft is None:
            ft = FrameTypeState(
                frame_key=frame_key,
                delimiter=delimiter,
                byte_length=len(payload),
            )
            st.frame_types[frame_key] = ft

        if ft.last_received_ts > 0:
            dt = now - ft.last_received_ts
            if 0.1 < dt < 120.0:
                ft.interval_sec = dt if ft.interval_sec == 0 else (0.7 * ft.interval_sec + 0.3 * dt)
        ft.last_received_ts = now
        ft.frame_count += 1
        ft.last_decrypted_text = decrypted_text
        if parsed:
            ft.last_parsed = parsed
            if "syncCode" in parsed:
                st.decoded_telemetry["syncCode"] = parsed["syncCode"]
            data_fields = parsed.get("data") or {}
            for k, v in data_fields.items():
                st.decoded_telemetry[k] = v

        # Split into 8-byte blocks
        num_blocks = (len(payload) + 7) // 8
        while len(ft.blocks) < num_blocks:
            idx = len(ft.blocks)
            ft.blocks.append(BlockSlotState(index=idx, current_hex=""))

        for i in range(num_blocks):
            blk_bytes = payload[i * 8 : (i + 1) * 8]
            hex_str = blk_bytes.hex(" ")
            dec_blk = xtea_decrypt_block(blk_bytes) if len(blk_bytes) == 8 else b""
            ascii_str = repr(dec_blk.decode("latin1", errors="replace"))[1:-1]

            slot = ft.blocks[i]
            if not slot.annotation:
                slot.annotation = self._default_block_annotation(frame_key, i, num_blocks, ascii_str)

            if not slot.current_hex:
                slot.current_hex = hex_str
                slot.current_ascii = ascii_str
                slot.seen_values.append(hex_str)
            elif slot.current_hex != hex_str:
                old_hex = slot.current_hex
                old_ascii = slot.current_ascii
                slot.previous_hex = old_hex
                slot.previous_ascii = old_ascii
                slot.current_hex = hex_str
                slot.current_ascii = ascii_str
                slot.change_count += 1
                slot.last_changed_ts = now
                if hex_str not in slot.seen_values:
                    slot.seen_values.append(hex_str)
                    if len(slot.seen_values) > 12:
                        slot.seen_values.pop(0)
                ts_str = time.strftime("%H:%M:%S", time.localtime(now))
                evt = (
                    f"[{ts_str}] {frame_key}[#{i:02d}] '{old_ascii}' -> '{ascii_str}'  "
                    f"({old_hex} -> {hex_str})"
                )
                st.recent_events.insert(0, evt)
                if len(st.recent_events) > 40:
                    st.recent_events.pop()
                self._recent_block_changes.append((now, host, frame_key, i, old_hex, hex_str))
                if len(self._recent_block_changes) > 100:
                    self._recent_block_changes.pop(0)
                self.block_changed.emit(host, frame_key, i, old_hex, hex_str)

    @staticmethod
    def _default_block_annotation(frame_key: str, block_idx: int, total_blocks: int, ascii_str: str = "") -> str:
        if ascii_str:
            return f'XTEA Plaintext: "{ascii_str}"'
        if frame_key.startswith("A_"):
            if block_idx in (0, 1, 2):
                return "Shared Protocol Header ('{type:primaryinfo,data:{')"
            return f"Device Telemetry Block #{block_idx - 2}"
        if frame_key.startswith("B_"):
            if block_idx in (0, 1):
                return "Heartbeat Header ('{type:OK,syncCod')"
            if block_idx in (2, 3):
                return "Device Identity / SyncCode Block"
        return "XTEA 64-bit ECB Block"

    async def _monitor_host_loop(self, host: str) -> None:
        st = self.states[host]
        try:
            loop = asyncio.get_running_loop()
            fqdn = await loop.run_in_executor(None, socket.getfqdn, host)
            if fqdn and fqdn != host:
                st.hostname = fqdn
        except Exception:
            pass

        while self._running:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, self.port), timeout=4.0
                )
                st.connected = True
                st.last_error = ""
                self.state_updated.emit()

                buf = bytearray()
                last_ui_emit = 0.0
                while self._running:
                    chunk = await asyncio.wait_for(reader.read(512), timeout=15.0)
                    if not chunk:
                        raise ConnectionResetError("Remote device closed port 2000 stream")
                    st.bytes_received += len(chunk)
                    st.last_seen_ts = time.time()
                    buf.extend(chunk)

                    if buf.endswith(b"<<<"):
                        await asyncio.sleep(0.03)
                        try:
                            extra = await asyncio.wait_for(reader.read(64), timeout=0.02)
                            if extra:
                                st.bytes_received += len(extra)
                                buf.extend(extra)
                        except asyncio.TimeoutError:
                            pass

                    frames = parse_delimited_frames(buf, flush_trailing=False)
                    if frames:
                        for payload, delim in frames:
                            self.ingest_frame(host, payload, delim)
                        self.state_updated.emit()
                        last_ui_emit = time.monotonic()
                    elif time.monotonic() - last_ui_emit > 1.0:
                        self.state_updated.emit()
                        last_ui_emit = time.monotonic()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                st.connected = False
                st.last_error = f"{type(exc).__name__}: {exc}"
                self.state_updated.emit()
                await asyncio.sleep(3.0)
            finally:
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass
