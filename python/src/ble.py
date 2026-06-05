"""
BLE Discovery Module - Discover ESP32 via Bluetooth Low Energy
"""

import sys
import asyncio

# Try to import bleak, but don't fail if not installed
try:
    from bleak import BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    BleakScanner = None

# ESP32 BLE Service UUID for GWASOAT Attendance System
ESP32_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
ESP32_DEVICE_NAME_PREFIX = "GWASOAT-Device"  # BLE device name prefix


async def scan_ble_devices(timeout=5):
    """
    Scan for nearby BLE devices and return ESP32 if found.
    
    Args:
        timeout: Scan duration in seconds
    
    Returns:
        List of discovered BLE devices with their info
    """
    if not BLEAK_AVAILABLE:
        return []
    
    try:
        devices = await BleakScanner.discover(timeout=timeout)
        esp32_devices = []
        
        for device in devices:
            # Look for ESP32 device by name
            if device.name and ESP32_DEVICE_NAME_PREFIX in device.name:
                esp32_devices.append({
                    'name': device.name,
                    'address': device.address,
                    'rssi': device.rssi
                })
        
        return esp32_devices
    except Exception as e:
        print(f"[BLE] Error scanning for devices: {e}")
        return []


def discover_esp32_ble(timeout=10):
    """
    Synchronous wrapper to discover ESP32 via BLE.
    
    Args:
        timeout: Total scan timeout in seconds
    
    Returns:
        Dict with ESP32 BLE info or None if not found
    """
    if not BLEAK_AVAILABLE:
        return {
            'status': 'error',
            'message': 'Bleak library not installed. Install with: pip install bleak'
        }
    
    try:
        # Try to use existing event loop, or create new one
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the scan
        if sys.platform == 'win32':
            # Windows specific handling
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        devices = loop.run_until_complete(scan_ble_devices(timeout=timeout))
        
        if devices:
            # Return the device with strongest signal (highest RSSI)
            best_device = max(devices, key=lambda d: d.get('rssi', -100))
            return {
                'status': 'success',
                'device_name': best_device['name'],
                'device_address': best_device['address'],
                'signal_strength': best_device['rssi']
            }
        
        return {
            'status': 'not_found',
            'message': 'No ESP32 BLE devices found'
        }
    
    except Exception as e:
        return {
            'status': 'error',
            'message': f'BLE scan failed: {str(e)}'
        }


def get_ble_status():
    """Get BLE module status and availability."""
    try:
        import bleak
        return {
            'available': True,
            'version': bleak.__version__,
            'message': 'BLE module ready'
        }
    except ImportError:
        return {
            'available': False,
            'message': 'Bleak library not installed. Install with: pip install bleak'
        }


if __name__ == "__main__":
    # Test BLE discovery
    print("Testing BLE Discovery...")
    print(f"BLE Status: {get_ble_status()}")
    print("Scanning for ESP32 BLE devices...")
    result = discover_esp32_ble(timeout=10)
    print(f"Result: {result}")
