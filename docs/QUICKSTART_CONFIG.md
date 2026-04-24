# Quick Start: Using the New Configuration System

## For End Users (Non-Developers)

### Changing Wi-Fi Settings (Teacher App)

1. Open the Teacher App on your computer
2. Navigate to the **Network Settings** page
3. Enter new WiFi SSID and password
4. Click **Update**
5. The app will reconnect to the ESP32 automatically

That's it! No code changes needed.

### Changing Wi-Fi Settings (BLE - Coming Soon)

1. Connect to device via Bluetooth app
2. Write configuration in JSON format:
```json
{
  "wifi_ssid": "MyNewNetwork",
  "wifi_password": "MyPassword123"
}
```
3. Changes apply immediately after disconnect/reconnect

## For Developers

### Testing Configuration Changes

**Python Side:**
```python
from config import get_config

cfg = get_config()

# Get current config
print(cfg.get("esp32_ip"))

# Change config
cfg.set("esp32_ip", "192.168.0.150")

# Verify change persisted
print(cfg.get("esp32_ip"))

# Get all available hosts
hosts = cfg.get_esp32_hosts()
print(hosts)  # ['192.168.0.150', '192.168.0.102', 'esp32.local']
```

**C++ Side:**
```cpp
ConfigManager cfg;
cfg.loadConfig();

// Get WiFi credentials
String ssid = cfg.getWiFiSSID();
String password = cfg.getWiFiPassword();

// Update settings
cfg.setWiFiCredentials("NewNetwork", "NewPassword");
cfg.setNetworkSettings("192.168.0.150", "192.168.0.1", "255.255.255.0");

// Serial will show [CONFIG] messages
```

### Using the REST API

**Get current network settings:**
```bash
curl http://localhost:5000/api/network
```

**Update network settings:**
```bash
curl -X POST http://localhost:5000/api/network \
  -d "esp32_ip=192.168.0.150" \
  -d "esp32_use_mdns=1"
```

**Response:**
```json
{
  "status": "success"
}
```

## Default Configuration

If you want to reset everything to defaults:

**Python:**
```python
cfg = get_config()
cfg.reset_to_defaults()
```

**C++:**
```cpp
cfg.resetToDefaults()  // Resets and saves to SPIFFS
```

## File Locations

- **Python Config Storage:** `attendance.db` (SQLite table `app_settings`)
- **C++ Config Storage:** `/config.json` on ESP32 SPIFFS
- **Documentation:** `CONFIGURATION.md` in project root

## Troubleshooting

**Q: Settings changed but device won't connect**
A: Check that IP address and subnet are correct for your network. Try auto-discovery via `/api/network/discover`.

**Q: Changes don't persist after restart**
A: Python: Check database permissions. C++: Check SPIFFS has space.

**Q: Device shows old Wi-Fi network**
A: Clear AP cache and reboot. Check serial output for loaded config.

## Next: BLE Configuration

When enabled via BLE, you'll be able to:
1. Discover device via Bluetooth
2. Send configuration wirelessly
3. No USB cable required
4. Multiple devices can be configured at once

See `CONFIGURATION.md` for BLE details.
