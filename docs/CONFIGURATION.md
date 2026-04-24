# GWASOAT Configuration System

## Overview

This document describes the centralized configuration system for the GWASOAT attendance system, which allows easy management of Wi-Fi credentials, IP addresses, and network settings without modifying code.

## Architecture

### Python (teacher_app.py)

The Python side uses a `ConfigManager` class in `config.py` that:
- Stores settings in SQLite database (`app_settings` table)
- Provides thread-safe access via `get()` and `set()` methods
- Maintains a global singleton instance accessed via `get_config()`

**Key Methods:**
- `get(key, default)` - Get a configuration value
- `set(key, value)` - Set a configuration value
- `get_esp32_hosts()` - Get list of ESP32 hosts in priority order
- `get_wifi_credentials()` - Get Wi-Fi SSID and password pair
- `set_wifi_credentials(ssid, password)` - Set Wi-Fi credentials

**Usage Example:**
```python
from config import get_config

cfg = get_config()
esp32_ip = cfg.get("esp32_ip", "192.168.0.102")
cfg.set("esp32_ip", "192.168.0.103")
```

### C++ (ESP32)

The C++ side uses a `ConfigManager` class in `include/config.h` that:
- Stores settings in SPIFFS filesystem (`/config.json`)
- Persists configuration across power cycles
- Loads defaults if config file doesn't exist
- Provides simple getter/setter methods

**Key Methods:**
- `get(key, default)` - Get a configuration value
- `set(key, value)` - Set a configuration value
- `getWiFiSSID()`, `getWiFiPassword()` - Get Wi-Fi credentials
- `getStaticIP()`, `getGateway()`, `getSubnet()` - Get network settings
- `setWiFiCredentials(ssid, password)` - Set Wi-Fi credentials
- `setNetworkSettings(ip, gateway, subnet)` - Set network settings
- `resetToDefaults()` - Reset all settings to defaults
- `loadConfig()` / `saveConfig()` - Manual save/load operations

**Usage Example:**
```cpp
ConfigManager cfg;
cfg.loadConfig();
String ssid = cfg.getWiFiSSID();
cfg.setWiFiCredentials("NewSSID", "NewPassword");
```

## Configuration Keys

| Key | Default | Description |
|-----|---------|-------------|
| `esp32_ip` | `192.168.0.102` | Static IP of ESP32 device |
| `esp32_use_mdns` | `0` | Enable mDNS discovery (0=disabled, 1=enabled) |
| `wifi_ssid` | `Vaswani_2.4` | Wi-Fi network name |
| `wifi_password` | `*******` | Wi-Fi network password |
| `static_ip` | `192.168.0.102` | Static IP for ESP32 |
| `gateway` | `192.168.0.1` | Network gateway |
| `subnet` | `255.255.255.0` | Network subnet mask |
| `active_class_id` | `` | Currently active class ID |
| `active_session_id` | `` | Currently active session ID |

## Changing Configuration

### Python Side

Via the Flask API endpoint `/api/network`:

**GET** - Retrieve current network settings:
```bash
curl http://localhost:5000/api/network
```

**POST** - Update network settings:
```bash
curl -X POST http://localhost:5000/api/network \
  -d "esp32_ip=192.168.0.103" \
  -d "esp32_use_mdns=1"
```

### C++ Side (ESP32)

#### Via BLE (Recommended for End-Users)

Connect via BLE and send JSON configuration:
```json
{
  "wifi_ssid": "NewNetwork",
  "wifi_password": "NewPassword",
  "static_ip": "192.168.0.105",
  "gateway": "192.168.0.1",
  "subnet": "255.255.255.0"
}
```

#### Via Serial Monitor (Development)

Send configuration commands:
```
set wifi_ssid YourNetwork
set wifi_password YourPassword
set static_ip 192.168.0.105
```

#### Via Web API (if configured)

Create web endpoints to modify SPIFFS config file.

## Migration from Hardcoded Values

**Before:**
```cpp
const char* WIFI_SSID = "Vaswani_2.4";
const char* WIFI_PASSWORD = "*******";
IPAddress localIP(192, 168, 0, 102);
```

**After:**
```cpp
ConfigManager config_manager;
config_manager.loadConfig();
String ssid = config_manager.getWiFiSSID();
IPAddress ip;
ip.fromString(config_manager.getStaticIP());
```

## Bluetooth Low Energy (BLE) Integration

BLE connectivity has been added to the system for wireless configuration. The BLE service is defined in `include/ble_service.h`.

### Features

- Device discovery via BLE broadcast
- Remote configuration of Wi-Fi credentials and IP settings
- Status updates via BLE notifications
- No code recompilation needed for configuration changes

### Building with BLE

BLE is enabled by default in `platformio.ini`:

```ini
build_flags = 
  -DBLE_ENABLED=1
```

To disable BLE, remove the flag or set `BLE_ENABLED=0`.

### BLE Service UUIDs

- **Service UUID:** `12345678-1234-1234-1234-123456789012`
- **Config Read:** `11111111-1111-1111-1111-111111111111`
- **Config Write:** `22222222-2222-2222-2222-222222222222`
- **Status:** `33333333-3333-3333-3333-333333333333`

## Best Practices

1. **Use ConfigManager instead of hardcoded values** - Ensures consistency
2. **Load config early in startup** - ESP32 should load config in `setup()`
3. **Validate input** - Always validate configuration values before using
4. **Test configuration changes** - Verify network connectivity after changes
5. **Back up important settings** - Export configuration for recovery
6. **Use environment variables** - For sensitive data like passwords

## Troubleshooting

### Configuration not persisting

**Python:** Check if database exists and has write permissions
**C++:** Check if SPIFFS is initialized and has available space

### Wrong configuration loaded

**Python:** Run `cfg = get_config(); cfg.get_all()` to verify stored values
**C++:** Check serial output for `[CONFIG]` messages

### Network connectivity issues after config change

1. Verify IP address is valid and on correct subnet
2. Check gateway and subnet mask match network
3. Try resetting to defaults with `resetToDefaults()`

## Future Enhancements

- Web dashboard for configuration management
- Configuration backup/restore functionality
- Scheduled configuration sync between Python and C++
- Encrypted storage for sensitive credentials
- Multi-network Wi-Fi support
