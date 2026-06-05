"""
WiFi Manager for GWASOAT.
Handles automatic IP switching based on connected WiFi network,
and can connect to the ESP32 hotspot for offline mode.
"""

import subprocess
import time
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import get_config

# Known WiFi → ESP32 IP mappings
ESP32_HOTSPOT_SSID = "GWASOAT-Device"
ESP32_HOTSPOT_PASSWORD = "Attend1234"
ESP32_HOTSPOT_IP = "192.168.4.1"

# Default IP when on home/school router
DEFAULT_ROUTER_IP = "192.168.0.103"


def get_current_ssid():
    """Get the currently connected WiFi SSID on Windows."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line.startswith("SSID") and "BSSID" not in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return None


def connect_to_hotspot():
    """
    Connect Windows WiFi to the ESP32 hotspot.
    Creates a WiFi profile if it doesn't exist, then connects.
    Returns True if connection succeeded.
    """
    ssid = ESP32_HOTSPOT_SSID
    password = ESP32_HOTSPOT_PASSWORD

    # Create WiFi profile XML
    profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""

    # Write profile to temp file
    profile_path = os.path.join(os.environ.get("TEMP", "."), "gwasoat_wifi.xml")
    try:
        with open(profile_path, "w") as f:
            f.write(profile_xml)

        # Add profile
        subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={profile_path}"],
            capture_output=True, timeout=10
        )

        # Connect
        result = subprocess.run(
            ["netsh", "wlan", "connect", f"name={ssid}"],
            capture_output=True, text=True, timeout=10
        )

        # Wait for connection
        for _ in range(10):
            time.sleep(1)
            current = get_current_ssid()
            if current == ssid:
                return True

        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        print(f"[WIFI] Failed to connect to hotspot: {e}")
        return False
    finally:
        try:
            os.remove(profile_path)
        except OSError:
            pass


def get_ip_for_current_network():
    """
    Determine the correct ESP32 IP based on current WiFi network.
    Returns the IP address string.
    """
    ssid = get_current_ssid()
    if ssid is None:
        # No WiFi connected — return last known IP
        return get_config().get("esp32_ip", DEFAULT_ROUTER_IP)

    if ssid == ESP32_HOTSPOT_SSID:
        return ESP32_HOTSPOT_IP

    # On any other network, use the configured router IP
    cfg = get_config()
    saved_router_ip = cfg.get("router_esp32_ip", "").strip()
    if saved_router_ip:
        return saved_router_ip
    return cfg.get("esp32_ip", DEFAULT_ROUTER_IP)


def auto_sync_ip():
    """
    Check current WiFi and update ESP32 IP setting if needed.
    Call this periodically or on network change.
    Returns dict with current state.
    """
    cfg = get_config()
    ssid = get_current_ssid()
    correct_ip = get_ip_for_current_network()
    current_ip = cfg.get("esp32_ip", "")

    changed = False
    if correct_ip != current_ip:
        # Save the old IP as router IP before switching
        if current_ip and current_ip != ESP32_HOTSPOT_IP:
            cfg.set("router_esp32_ip", current_ip)
        cfg.set("esp32_ip", correct_ip)
        changed = True

    from network import set_last_working_host
    set_last_working_host(correct_ip)

    return {
        "ssid": ssid or "Not connected",
        "esp32_ip": correct_ip,
        "changed": changed,
        "mode": "offline" if ssid == ESP32_HOTSPOT_SSID else "online"
    }
