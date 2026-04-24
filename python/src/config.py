"""
Centralized configuration management for GWASOAT.
Manages all settings: Wi-Fi, IP, network hosts, and application preferences.
"""

import sqlite3
import threading
from typing import Optional, List, Dict, Any

# Default configuration values
DEFAULTS = {
    "esp32_ip": "192.168.0.102",
    "esp32_use_mdns": "0",
    "wifi_ssid": "",
    "wifi_password": "",
    "active_class_id": "",
    "active_session_id": "",
}


class ConfigManager:
    """Thread-safe configuration manager using SQLite backend."""

    def __init__(self, db_path: str = "attendance.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._initialize_settings_table()

    def _get_db(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def _initialize_settings_table(self) -> None:
        """Ensure settings table exists."""
        with self._lock:
            db = self._get_db()
            db.execute(
                """CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            # Initialize defaults if not present
            for key, default_value in DEFAULTS.items():
                db.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                    (key, default_value),
                )
            db.commit()
            db.close()

    def get(self, key: str, default: str = "") -> str:
        """Get a configuration value."""
        with self._lock:
            db = self._get_db()
            row = db.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            db.close()
            if row is None:
                return default if default else DEFAULTS.get(key, "")
            return row["value"].strip() if row["value"] else default

    def set(self, key: str, value: str) -> None:
        """Set a configuration value."""
        with self._lock:
            db = self._get_db()
            db.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
            db.commit()
            db.close()

    def get_all(self) -> Dict[str, str]:
        """Get all configuration as dictionary."""
        with self._lock:
            db = self._get_db()
            rows = db.execute("SELECT key, value FROM app_settings").fetchall()
            db.close()
            return {row["key"]: row["value"] for row in rows}

    def get_esp32_hosts(self) -> List[str]:
        """Get list of ESP32 hosts to try, in priority order."""
        hosts = []
        
        # Add configured IP first
        configured_ip = self.get("esp32_ip").strip()
        if configured_ip:
            hosts.append(configured_ip)

        # Add mDNS if enabled
        if self.get("esp32_use_mdns") == "1" and "esp32.local" not in hosts:
            hosts.append("esp32.local")

        # Add fallback hosts
        for fallback in ["192.168.0.102", "esp32.local"]:
            if fallback not in hosts:
                hosts.append(fallback)

        return hosts

    def get_wifi_credentials(self) -> tuple[str, str]:
        """Get Wi-Fi SSID and password."""
        return (
            self.get("wifi_ssid"),
            self.get("wifi_password"),
        )

    def set_wifi_credentials(self, ssid: str, password: str) -> None:
        """Set Wi-Fi credentials."""
        self.set("wifi_ssid", ssid)
        self.set("wifi_password", password)

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        with self._lock:
            db = self._get_db()
            for key, value in DEFAULTS.items():
                db.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            db.commit()
            db.close()


# Global config instance
_config: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get or create global config manager instance."""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config
