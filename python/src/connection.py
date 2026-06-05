"""
Hybrid WiFi + BLE Connection Manager for GWASOAT.
Automatically falls back to BLE when WiFi is unavailable.
"""

import asyncio
import json
import threading
import time
import base64
from typing import Optional, Dict, Any, Callable

import requests

# BLE support (optional - graceful degradation if not installed)
try:
    import bleak
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False
    print("[CONN] bleak not installed - BLE support disabled")


# BLE UUIDs (must match firmware)
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CMD_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
RESP_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a9"
TEMPLATE_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26aa"
STATUS_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26ab"

BLE_DEVICE_NAME = "GWASOAT-Device"


class ConnectionManager:
    """Manages WiFi and BLE connections to ESP32 device."""

    def __init__(self):
        self.mode = "wifi"  # "wifi" or "ble"
        self.wifi_host = None
        self.wifi_healthy = False
        self.ble_client = None
        self.ble_connected = False
        self.ble_address = None
        self._lock = threading.Lock()
        self._status_callback = None
        self._ble_loop = None
        self._ble_thread = None
        self._last_ble_response = None
        self._ble_response_event = threading.Event()

    def set_wifi_host(self, host: str):
        """Set the WiFi host address."""
        self.wifi_host = host

    def set_status_callback(self, callback: Callable):
        """Set callback for BLE status notifications."""
        self._status_callback = callback

    # ─── WiFi Methods ────────────────────────────────────────

    def _wifi_request(self, path: str, method: str = "GET",
                      params: dict = None, json_data: dict = None,
                      timeout: float = 5.0) -> Optional[Dict]:
        """Make HTTP request to ESP32 over WiFi."""
        if not self.wifi_host:
            return None
        url = f"http://{self.wifi_host}{path}"
        try:
            if method == "POST":
                resp = requests.post(url, json=json_data, params=params,
                                     timeout=timeout)
            else:
                resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                self.wifi_healthy = True
                try:
                    return resp.json()
                except ValueError:
                    return {"raw": resp.text}
            return None
        except requests.RequestException:
            self.wifi_healthy = False
            return None

    def wifi_health_check(self) -> bool:
        """Check if WiFi connection to ESP32 is alive."""
        result = self._wifi_request("/status", timeout=2.0)
        self.wifi_healthy = result is not None
        return self.wifi_healthy

    # ─── BLE Methods ─────────────────────────────────────────

    def _start_ble_loop(self):
        """Start asyncio event loop for BLE in background thread."""
        if not BLE_AVAILABLE:
            return
        if self._ble_thread and self._ble_thread.is_alive():
            return
        self._ble_loop = asyncio.new_event_loop()
        self._ble_thread = threading.Thread(
            target=self._run_ble_loop, daemon=True
        )
        self._ble_thread.start()

    def _run_ble_loop(self):
        """Run the BLE asyncio loop."""
        asyncio.set_event_loop(self._ble_loop)
        self._ble_loop.run_forever()

    def _run_async(self, coro):
        """Run an async coroutine from sync context."""
        if not self._ble_loop:
            self._start_ble_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._ble_loop)
        return future.result(timeout=30)

    async def _ble_scan_and_connect(self) -> bool:
        """Scan for GWASOAT device and connect."""
        if not BLE_AVAILABLE:
            return False
        try:
            devices = await bleak.BleakScanner.discover(timeout=5.0)
            for d in devices:
                if d.name and BLE_DEVICE_NAME in d.name:
                    self.ble_address = d.address
                    break
            if not self.ble_address:
                print("[BLE] Device not found")
                return False

            self.ble_client = bleak.BleakClient(self.ble_address)
            await self.ble_client.connect()
            self.ble_connected = self.ble_client.is_connected

            if self.ble_connected:
                # Subscribe to status notifications
                await self.ble_client.start_notify(
                    STATUS_CHAR_UUID, self._ble_notification_handler
                )
                # Subscribe to response notifications
                await self.ble_client.start_notify(
                    RESP_CHAR_UUID, self._ble_response_handler
                )
                print(f"[BLE] Connected to {self.ble_address}")
            return self.ble_connected
        except Exception as e:
            print(f"[BLE] Connection failed: {e}")
            self.ble_connected = False
            return False

    def _ble_notification_handler(self, sender, data: bytearray):
        """Handle BLE status notifications."""
        try:
            msg = json.loads(data.decode())
            if self._status_callback:
                self._status_callback(msg)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    def _ble_response_handler(self, sender, data: bytearray):
        """Handle BLE command responses."""
        try:
            self._last_ble_response = json.loads(data.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._last_ble_response = {"raw": data.decode()}
        self._ble_response_event.set()

    async def _ble_send_command(self, cmd: dict) -> Optional[Dict]:
        """Send command over BLE and wait for response."""
        if not self.ble_connected or not self.ble_client:
            return None
        try:
            self._ble_response_event.clear()
            self._last_ble_response = None
            payload = json.dumps(cmd).encode()
            await self.ble_client.write_gatt_char(CMD_CHAR_UUID, payload)
            # Wait for response notification
            got_response = self._ble_response_event.wait(timeout=15.0)
            if got_response:
                return self._last_ble_response
            return None
        except Exception as e:
            print(f"[BLE] Send failed: {e}")
            self.ble_connected = False
            return None

    def connect_ble(self) -> bool:
        """Connect to ESP32 via BLE (blocking)."""
        if not BLE_AVAILABLE:
            return False
        self._start_ble_loop()
        return self._run_async(self._ble_scan_and_connect())

    def disconnect_ble(self):
        """Disconnect BLE."""
        if self.ble_client and self.ble_connected:
            try:
                self._run_async(self.ble_client.disconnect())
            except Exception:
                pass
        self.ble_connected = False

    # ─── Unified Send (Auto-failover) ───────────────────────

    def send_command(self, cmd: dict, timeout: float = 10.0) -> Optional[Dict]:
        """
        Send command to ESP32 using best available transport.
        Tries WiFi first, falls back to BLE.
        """
        with self._lock:
            # Try WiFi first
            if self.wifi_host and self.wifi_healthy:
                result = self._wifi_request(
                    "/command", method="POST", json_data=cmd, timeout=timeout
                )
                if result is not None:
                    self.mode = "wifi"
                    return result

            # WiFi failed - try BLE
            if BLE_AVAILABLE:
                if not self.ble_connected:
                    self.connect_ble()
                if self.ble_connected:
                    result = self._run_async(self._ble_send_command(cmd))
                    if result is not None:
                        self.mode = "ble"
                        return result

            # Last resort: try WiFi without health check
            if self.wifi_host:
                result = self._wifi_request(
                    "/command", method="POST", json_data=cmd, timeout=timeout
                )
                if result is not None:
                    self.mode = "wifi"
                    self.wifi_healthy = True
                    return result

            return None

    def send_template(self, class_id: int, student_id: int,
                      name: str, template_bytes: bytes) -> bool:
        """
        Send a fingerprint template to ESP32.
        Uses WiFi for speed, falls back to BLE (chunked).
        """
        b64 = base64.b64encode(template_bytes).decode()

        # Try WiFi first (can send full template in one request)
        if self.wifi_host and self.wifi_healthy:
            cmd = {
                "cmd": "upload_template",
                "student_id": student_id,
                "class_id": class_id,
                "name": name,
                "template": b64
            }
            result = self._wifi_request(
                "/command", method="POST", json_data=cmd, timeout=10.0
            )
            if result and result.get("status") == "success":
                return True

        # BLE chunked transfer
        if BLE_AVAILABLE and self.ble_connected:
            return self._send_template_ble(student_id, template_bytes)

        return False

    def _send_template_ble(self, student_id: int, data: bytes) -> bool:
        """Send template over BLE in chunks."""
        chunk_size = 500  # Stay under MTU
        total_chunks = (len(data) + chunk_size - 1) // chunk_size

        async def _send():
            for i in range(total_chunks):
                offset = i * chunk_size
                chunk = data[offset:offset + chunk_size]
                # Header: student_id(2) + chunk_num(1) + total(1) + data
                header = bytes([
                    (student_id >> 8) & 0xFF,
                    student_id & 0xFF,
                    i & 0xFF,
                    total_chunks & 0xFF
                ])
                payload = header + chunk
                await self.ble_client.write_gatt_char(
                    TEMPLATE_CHAR_UUID, payload
                )
                await asyncio.sleep(0.05)
            return True

        try:
            return self._run_async(_send())
        except Exception as e:
            print(f"[BLE] Template send failed: {e}")
            return False

    # ─── Convenience Methods ─────────────────────────────────

    def get_status(self) -> Optional[Dict]:
        return self.send_command({"cmd": "status"})

    def register_fingerprint(self, student_id: int, name: str,
                             class_id: int = 0) -> Optional[Dict]:
        return self.send_command({
            "cmd": "register",
            "id": student_id,
            "name": name,
            "class_id": class_id
        })

    def get_register_status(self) -> Optional[Dict]:
        return self.send_command({"cmd": "register_status"})

    def get_template(self, student_id: int) -> Optional[Dict]:
        return self.send_command({"cmd": "get_template", "id": student_id},
                                timeout=15.0)

    def load_class(self, class_id: int,
                   students: list = None) -> Optional[Dict]:
        cmd = {"cmd": "load_class", "class_id": class_id}
        if students:
            cmd["students"] = students
        return self.send_command(cmd, timeout=30.0)

    def start_attendance(self) -> Optional[Dict]:
        return self.send_command({"cmd": "start_attendance"})

    def stop_attendance(self) -> Optional[Dict]:
        return self.send_command({"cmd": "stop_attendance"})

    def get_attendance(self) -> Optional[Dict]:
        return self.send_command({"cmd": "get_attendance"})

    def mark_attendance(self) -> Optional[Dict]:
        return self.send_command({"cmd": "attendance"}, timeout=12.0)

    def set_wifi_config(self, ssid: str, password: str,
                        static_ip: str = "") -> Optional[Dict]:
        cmd = {"cmd": "set_wifi", "ssid": ssid, "password": password}
        if static_ip:
            cmd["static_ip"] = static_ip
        return self.send_command(cmd)

    def get_connection_info(self) -> Dict:
        """Get current connection state."""
        return {
            "mode": self.mode,
            "wifi_host": self.wifi_host,
            "wifi_healthy": self.wifi_healthy,
            "ble_connected": self.ble_connected,
            "ble_address": self.ble_address,
            "ble_available": BLE_AVAILABLE
        }


# Global instance
_connection: Optional[ConnectionManager] = None


def get_connection() -> ConnectionManager:
    """Get or create global connection manager."""
    global _connection
    if _connection is None:
        _connection = ConnectionManager()
    return _connection
