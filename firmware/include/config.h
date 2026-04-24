#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <SPIFFS.h>

/**
 * Centralized configuration management for ESP32.
 * Stores Wi-Fi credentials and network settings in SPIFFS.
 */

class ConfigManager {
private:
    static const char* CONFIG_FILE;
    DynamicJsonDocument config;

public:
    ConfigManager() : config(512) {
        loadConfig();
    }

    void loadConfig() {
        if (!SPIFFS.exists(CONFIG_FILE)) {
            Serial.println("[CONFIG] No config file found, using defaults");
            config["wifi_ssid"] = "Vaswani_2.4";
            config["wifi_password"] = "*******";
            config["static_ip"] = "192.168.0.102";
            config["gateway"] = "192.168.0.1";
            config["subnet"] = "255.255.255.0";
            config["use_mdns"] = false;
            saveConfig();
            return;
        }

        File file = SPIFFS.open(CONFIG_FILE, "r");
        if (!file) {
            Serial.println("[CONFIG] Failed to open config file");
            return;
        }

        DeserializationError error = deserializeJson(config, file);
        file.close();

        if (error) {
            Serial.print("[CONFIG] JSON parse error: ");
            Serial.println(error.c_str());
        } else {
            Serial.println("[CONFIG] Loaded config from SPIFFS");
        }
    }

    void saveConfig() {
        File file = SPIFFS.open(CONFIG_FILE, "w");
        if (!file) {
            Serial.println("[CONFIG] Failed to open config file for writing");
            return;
        }

        serializeJson(config, file);
        file.close();
        Serial.println("[CONFIG] Config saved to SPIFFS");
    }

    String get(const char* key, const String& defaultValue = "") const {
        if (config.containsKey(key)) {
            return config[key].as<String>();
        }
        return defaultValue;
    }

    void set(const char* key, const String& value) {
        config[key] = value;
        saveConfig();
    }

    void set(const char* key, bool value) {
        config[key] = value;
        saveConfig();
    }

    bool getBoolean(const char* key, bool defaultValue = false) const {
        if (config.containsKey(key)) {
            return config[key].as<bool>();
        }
        return defaultValue;
    }

    String getWiFiSSID() const {
        return get("wifi_ssid", "Vaswani_2.4");
    }

    String getWiFiPassword() const {
        return get("wifi_password", "*******");
    }

    String getStaticIP() const {
        return get("static_ip", "192.168.0.102");
    }

    String getGateway() const {
        return get("gateway", "192.168.0.1");
    }

    String getSubnet() const {
        return get("subnet", "255.255.255.0");
    }

    bool getUseMDNS() const {
        return getBoolean("use_mdns", false);
    }

    void setWiFiCredentials(const String& ssid, const String& password) {
        set("wifi_ssid", ssid);
        set("wifi_password", password);
    }

    void setNetworkSettings(const String& ip, const String& gateway, const String& subnet) {
        set("static_ip", ip);
        set("gateway", gateway);
        set("subnet", subnet);
    }

    void resetToDefaults() {
        config.clear();
        config["wifi_ssid"] = "Vaswani_2.4";
        config["wifi_password"] = "*******";
        config["static_ip"] = "192.168.0.102";
        config["gateway"] = "192.168.0.1";
        config["subnet"] = "255.255.255.0";
        config["use_mdns"] = false;
        saveConfig();
    }

    JsonObject getAll() const {
        return config.as<JsonObject>();
    }
};

const char* ConfigManager::CONFIG_FILE = "/config.json";

#endif
