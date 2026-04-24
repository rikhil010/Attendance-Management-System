"""
Network and ESP32 communication module.
Handles all ESP32 device requests and network operations.
"""

import requests
import socket
import ipaddress
import concurrent.futures
from config import get_config

last_working_host = None


def set_last_working_host(host):
    """Update last working host."""
    global last_working_host
    last_working_host = host


def get_last_working_host():
    """Get last working host."""
    return last_working_host


def esp32_request(path, params=None, timeout=3):
    """Make HTTP request to ESP32 with intelligent host fallback."""
    global last_working_host
    cfg = get_config()
    hosts_from_settings = cfg.get_esp32_hosts()

    hosts_to_try = []
    if last_working_host:
        hosts_to_try.append(last_working_host)
    for host in hosts_from_settings:
        if host not in hosts_to_try:
            hosts_to_try.append(host)

    errors = []
    for host in hosts_to_try:
        url = f"http://{host}{path}"
        try:
            response = requests.get(url, params=params, timeout=timeout)
            last_working_host = host
            return response, host, None
        except requests.RequestException as ex:
            errors.append(f"{host}: {ex}")

    if not errors:
        errors.append("No ESP32 hosts configured")
    return None, None, " | ".join(errors)


def get_local_ipv4():
    """Get local machine's IPv4 address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def probe_esp32_host(host, timeout=0.35):
    """Probe a single ESP32 host for status."""
    try:
        response = requests.get(f"http://{host}/status", timeout=timeout)
        if response.status_code != 200:
            return None
        data = response.json()
        if "ap_ip" in data or "sta_connected" in data:
            return {"host": host, "status": data}
    except (requests.RequestException, ValueError):
        return None
    return None


def discover_esp32_host():
    """Discover ESP32 host on network with intelligent fallback."""
    cfg = get_config()
    
    # First, try likely hosts quickly
    likely_hosts = []
    for h in [last_working_host, cfg.get("esp32_ip"), "192.168.0.102"]:
        if h and h not in likely_hosts:
            likely_hosts.append(h)

    for host in likely_hosts:
        found = probe_esp32_host(host, timeout=0.6)
        if found:
            return found

    # Then scan current local /24 subnet
    local_ip = get_local_ipv4()
    if not local_ip:
        return None

    try:
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return None

    candidate_hosts = [str(ip) for ip in network.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as executor:
        futures = [
            executor.submit(probe_esp32_host, host, 0.25) 
            for host in candidate_hosts
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                return result

    return None
