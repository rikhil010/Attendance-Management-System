#ifndef BLE_SERVICE_H
#define BLE_SERVICE_H

#include <NimBLEDevice.h>
#include <ArduinoJson.h>

// BLE UUIDs
#define SERVICE_UUID            "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CMD_CHAR_UUID           "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define RESP_CHAR_UUID          "beb5483e-36e1-4688-b7f5-ea07361b26a9"
#define TEMPLATE_CHAR_UUID      "beb5483e-36e1-4688-b7f5-ea07361b26aa"
#define STATUS_CHAR_UUID        "beb5483e-36e1-4688-b7f5-ea07361b26ab"

// Forward declaration of the command processor
extern void processCommand(const String& jsonCmd, String& response);

// BLE globals
extern NimBLECharacteristic* pResponseChar;
extern NimBLECharacteristic* pStatusChar;
extern NimBLECharacteristic* pTemplateChar;
extern bool bleClientConnected;

// Template transfer state
struct TemplateTransfer {
    uint16_t studentId;
    uint8_t slotId;
    uint16_t totalBytes;
    uint16_t receivedBytes;
    uint8_t data[1024];  // Max template size
    bool inProgress;
};

extern TemplateTransfer bleTemplateTransfer;

// BLE Callbacks
class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer) override {
        bleClientConnected = true;
        Serial.println("[BLE] Client connected");
    }
    void onDisconnect(NimBLEServer* pServer) override {
        bleClientConnected = false;
        Serial.println("[BLE] Client disconnected");
        NimBLEDevice::startAdvertising();
    }
};

class CmdCharCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* pChar) override {
        std::string val = pChar->getValue();
        if (val.length() > 0) {
            String cmd = String(val.c_str());
            Serial.print("[BLE] Command received: ");
            Serial.println(cmd);
            String response;
            processCommand(cmd, response);
            if (pResponseChar) {
                pResponseChar->setValue(response.c_str());
                pResponseChar->notify();
            }
        }
    }
};

class TemplateCharCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* pChar) override;
};

// Initialize BLE
inline void initBLE(const char* deviceName) {
    NimBLEDevice::init(deviceName);
    NimBLEDevice::setMTU(517);

    NimBLEServer* pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());

    NimBLEService* pService = pServer->createService(SERVICE_UUID);

    // Command characteristic (write)
    NimBLECharacteristic* pCmdChar = pService->createCharacteristic(
        CMD_CHAR_UUID,
        NIMBLE_PROPERTY::WRITE
    );
    pCmdChar->setCallbacks(new CmdCharCallbacks());

    // Response characteristic (read + notify)
    pResponseChar = pService->createCharacteristic(
        RESP_CHAR_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );

    // Template transfer characteristic (write)
    pTemplateChar = pService->createCharacteristic(
        TEMPLATE_CHAR_UUID,
        NIMBLE_PROPERTY::WRITE
    );
    pTemplateChar->setCallbacks(new TemplateCharCallbacks());

    // Status characteristic (read + notify)
    pStatusChar = pService->createCharacteristic(
        STATUS_CHAR_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );

    pService->start();

    NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->start();

    Serial.println("[BLE] Service started, advertising...");
}

// Send status notification over BLE
inline void bleNotifyStatus(const String& json) {
    if (bleClientConnected && pStatusChar) {
        pStatusChar->setValue(json.c_str());
        pStatusChar->notify();
    }
}

#endif
