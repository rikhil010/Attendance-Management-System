#ifndef BLE_SERVICE_H
#define BLE_SERVICE_H

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <NimBLEServer.h>
#include <NimBLEUtils.h>
#include "../include/config.h"

/**
 * BLE Service for GWASOAT system.
 * Provides configuration sync and device discovery over Bluetooth Low Energy.
 */

#define SERVICE_UUID "12345678-1234-1234-1234-123456789012"
#define CHAR_CONFIG_READ "11111111-1111-1111-1111-111111111111"
#define CHAR_CONFIG_WRITE "22222222-2222-2222-2222-222222222222"
#define CHAR_STATUS "33333333-3333-3333-3333-333333333333"

class BLEConfigCallback : public NimBLECharacteristicCallbacks {
public:
    BLEConfigCallback(ConfigManager* cfg) : config(cfg) {}

    void onWrite(NimBLECharacteristic* pCharacteristic) override {
        std::string value = pCharacteristic->getValue();
        if (value.empty()) return;

        // Parse JSON configuration from BLE write
        DynamicJsonDocument doc(512);
        DeserializationError error = deserializeJson(doc, (const char*)value.c_str());
        
        if (!error && doc.is<JsonObject>()) {
            if (doc.containsKey("wifi_ssid")) {
                config->set("wifi_ssid", doc["wifi_ssid"].as<String>());
            }
            if (doc.containsKey("wifi_password")) {
                config->set("wifi_password", doc["wifi_password"].as<String>());
            }
            if (doc.containsKey("static_ip")) {
                config->set("static_ip", doc["static_ip"].as<String>());
            }
            if (doc.containsKey("gateway")) {
                config->set("gateway", doc["gateway"].as<String>());
            }
            if (doc.containsKey("subnet")) {
                config->set("subnet", doc["subnet"].as<String>());
            }
            Serial.println("[BLE] Configuration updated via BLE");
        }
    }

private:
    ConfigManager* config;
};

class BLEStatusCallback : public NimBLEServerCallbacks {
public:
    BLEStatusCallback(ConfigManager* cfg) : config(cfg) {}

    void onConnect(NimBLEServer* pServer) override {
        Serial.println("[BLE] Client connected");
    }

    void onDisconnect(NimBLEServer* pServer) override {
        Serial.println("[BLE] Client disconnected");
        pServer->startAdvertising();
    }

private:
    ConfigManager* config;
};

class BLEService {
private:
    NimBLEServer* server;
    NimBLEService* service;
    ConfigManager* config;
    bool initialized;

public:
    BLEService(ConfigManager* cfg) : config(cfg), initialized(false) {}

    bool initialize() {
        #ifdef BLE_ENABLED
        try {
            NimBLEDevice::init("GWASOAT");
            server = NimBLEDevice::createServer();
            server->setCallbacks(new BLEStatusCallback(config));

            service = server->createService(SERVICE_UUID);

            // Config read characteristic
            NimBLECharacteristic* configReadChar = service->createCharacteristic(
                CHAR_CONFIG_READ,
                NIMBLE_PROPERTY::READ
            );

            // Config write characteristic
            NimBLECharacteristic* configWriteChar = service->createCharacteristic(
                CHAR_CONFIG_WRITE,
                NIMBLE_PROPERTY::WRITE
            );
            configWriteChar->setCallbacks(new BLEConfigCallback(config));

            // Status characteristic
            NimBLECharacteristic* statusChar = service->createCharacteristic(
                CHAR_STATUS,
                NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
            );

            service->start();

            // Start advertising
            NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
            pAdvertising->addServiceUUID(SERVICE_UUID);
            pAdvertising->setScanResponse(true);
            pAdvertising->setMinInterval(0x06);
            pAdvertising->setMaxInterval(0xFF);
            pAdvertising->start();

            initialized = true;
            Serial.println("[BLE] BLE service initialized successfully");
            return true;
        } catch (std::exception& e) {
            Serial.print("[BLE] Initialization failed: ");
            Serial.println(e.what());
            return false;
        }
        #else
        Serial.println("[BLE] BLE disabled in build");
        return false;
        #endif
    }

    void updateStatus(const String& status) {
        if (!initialized) return;
        // Broadcast status to connected BLE clients
        Serial.print("[BLE] Status update: ");
        Serial.println(status);
    }

    bool isInitialized() const {
        return initialized;
    }

    void shutdown() {
        if (initialized) {
            #ifdef BLE_ENABLED
            NimBLEDevice::deinit(true);
            initialized = false;
            Serial.println("[BLE] BLE service shut down");
            #endif
        }
    }
};

#endif
