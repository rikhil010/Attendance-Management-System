#include <Arduino.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "pins.h"
#include "config.h"
#include "fingerprint.h"
#include "sd_cache.h"
#include "ble_service.h"

// ─── Hardware Objects ───────────────────────────────────────
HardwareSerial fingerSerial(2);
FingerprintSensor fp(fingerSerial);
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
AsyncWebServer server(80);
SDCache sdCache;
ConfigManager config_manager;

// ─── BLE Globals ────────────────────────────────────────────
NimBLECharacteristic* pResponseChar = nullptr;
NimBLECharacteristic* pStatusChar = nullptr;
NimBLECharacteristic* pTemplateChar = nullptr;
bool bleClientConnected = false;
TemplateTransfer bleTemplateTransfer = {0, 0, 0, 0, {0}, false};

// ─── State ──────────────────────────────────────────────────
bool attendance_mode = false;
bool sta_connected = false;
String registerState = "idle";
String registerDetail = "";
uint16_t registerTargetId = 0;
String registerTargetName = "";
TaskHandle_t registerTaskHandle = nullptr;

// Display timing
unsigned long displayHoldUntilMs = 0;
unsigned long attendanceFeedbackUntilMs = 0;
unsigned long lastIdleRefreshMs = 0;
bool attendancePromptVisible = false;
bool idleStatusVisible = false;
bool showIdleWifiPage = true;

// Class loading state
int loadedClassId = -1;
int loadedStudentCount = 0;

// Slot-to-student mapping (sensor slot → real student ID)
#define MAX_CLASS_SIZE 255
int slotToStudent[MAX_CLASS_SIZE];
String slotToName[MAX_CLASS_SIZE];

// Attendance buffer
DynamicJsonDocument attendance(4096);
DynamicJsonDocument studentRoster(4096);

// Fallback AP
const char* AP_SSID = "GWASOAT-Device";
const char* AP_PASSWORD = "Attend1234";

// ─── Display Functions ──────────────────────────────────────
void holdDisplayFor(uint32_t ms) { displayHoldUntilMs = millis() + ms; }

void displayMessage(const String& title, const String& msg = "") {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(title);
    if (msg.length() > 0) {
        display.setCursor(0, 20);
        display.setTextSize(2);
        display.println(msg);
    }
    display.display();
}

void displayIdleStatus() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("GWASOAT Ready");
    if (showIdleWifiPage) {
        display.setCursor(0, 16);
        display.println("WiFi: " + config_manager.getWiFiSSID());
        display.setCursor(0, 30);
        if (sta_connected) {
            display.println("IP: " + WiFi.localIP().toString());
        } else {
            display.println("AP: " + WiFi.softAPIP().toString());
        }
        display.setCursor(0, 46);
        display.println(bleClientConnected ? "BLE: Connected" : "BLE: Advertising");
    } else {
        display.setCursor(0, 16);
        if (loadedClassId >= 0) {
            display.println("Class: " + String(loadedClassId));
            display.setCursor(0, 30);
            display.println("Students: " + String(loadedStudentCount));
        } else {
            display.println("No class loaded");
        }
        display.setCursor(0, 46);
        String sdInfo = sdCache.isReady() ? "SD: OK" : "SD: Not found";
        display.println(sdInfo);
    }
    display.display();
    idleStatusVisible = true;
    attendancePromptVisible = false;
    lastIdleRefreshMs = millis();
    showIdleWifiPage = !showIdleWifiPage;
}

void displayAttendancePrompt() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Attendance Mode");
    display.setCursor(0, 16);
    display.println("Place finger on");
    display.setCursor(0, 28);
    display.println("sensor...");
    if (loadedClassId >= 0) {
        display.setCursor(0, 46);
        display.println("Class " + String(loadedClassId) + " (" + String(loadedStudentCount) + " students)");
    }
    display.display();
    attendancePromptVisible = true;
    idleStatusVisible = false;
}

void displayAttendanceResult(bool success, const String& name, int id) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    if (success) {
        display.println("Attendance Marked!");
        display.setCursor(0, 18);
        display.setTextSize(2);
        display.println(name.substring(0, 10));
        display.setTextSize(1);
        display.setCursor(0, 50);
        display.println("ID: " + String(id));
    } else {
        display.println("Not Recognized");
        display.setCursor(0, 20);
        display.println("Try again");
    }
    display.display();
    attendanceFeedbackUntilMs = millis() + (success ? 2000 : 2500);
    holdDisplayFor(success ? 2000 : 2500);
    attendancePromptVisible = false;
    idleStatusVisible = false;
}

// ─── Register State ─────────────────────────────────────────
void setRegisterState(const String& state, const String& detail = "") {
    registerState = state;
    registerDetail = detail;
    Serial.println("[REG] " + state + " | " + detail);
    // Notify BLE client
    DynamicJsonDocument doc(256);
    doc["event"] = "register_state";
    doc["state"] = state;
    doc["detail"] = detail;
    doc["id"] = registerTargetId;
    doc["name"] = registerTargetName;
    String json;
    serializeJson(doc, json);
    bleNotifyStatus(json);
}

bool isRegisterBusy() {
    return registerTaskHandle != nullptr ||
           (registerState != "idle" && registerState != "success" && registerState != "failed");
}

// ─── Template Management ────────────────────────────────────

// After enrollment, extract template and save to SD + return to caller
int extractAndSaveTemplate(uint16_t sensorSlot, int classId, int studentId) {
    // Load the template into buffer 1
    if (!fp.loadChar(1, sensorSlot)) {
        Serial.println("[TPL] loadChar failed");
        return -1;
    }
    delay(100);
    
    // Upload from sensor to ESP32
    uint8_t templateData[1024];
    int tplLen = fp.uploadTemplate(1, templateData, sizeof(templateData));
    if (tplLen <= 0) {
        Serial.println("[TPL] uploadTemplate failed");
        return -1;
    }
    
    // Save to SD card
    if (sdCache.isReady()) {
        sdCache.saveTemplate(classId, studentId, templateData, tplLen);
    }
    
    Serial.print("[TPL] Extracted and saved template, ");
    Serial.print(tplLen);
    Serial.println(" bytes");
    return tplLen;
}

// Load all templates for a class from SD into sensor
bool loadClassTemplates(int classId) {
    if (!sdCache.isReady()) {
        Serial.println("[TPL] SD not ready, cannot load class");
        return false;
    }
    
    displayMessage("Loading Class", String(classId));
    
    // Clear sensor
    fp.emptyDatabase();
    delay(200);
    
    // Get list of student IDs for this class
    int studentIds[MAX_CLASS_SIZE];
    int count = sdCache.listClassTemplates(classId, studentIds, MAX_CLASS_SIZE);
    
    Serial.print("[TPL] Found ");
    Serial.print(count);
    Serial.println(" templates on SD");
    
    int loaded = 0;
    uint8_t templateData[1024];
    
    for (int i = 0; i < count && i < MAX_CLASS_SIZE; i++) {
        int tplLen = sdCache.loadTemplate(classId, studentIds[i], templateData, sizeof(templateData));
        if (tplLen <= 0) continue;
        
        // Download template into sensor at slot i
        if (fp.downloadTemplate(1, templateData, tplLen)) {
            // Store in sensor flash at slot i
            if (fp.store(1, (uint16_t)i)) {
                slotToStudent[i] = studentIds[i];
                slotToName[i] = String(studentIds[i]);  // Name will be updated by roster
                loaded++;
            }
        }
        delay(50);
    }
    
    loadedClassId = classId;
    loadedStudentCount = loaded;
    
    displayMessage("Class Loaded", String(loaded) + " students");
    holdDisplayFor(1500);
    
    Serial.print("[TPL] Loaded ");
    Serial.print(loaded);
    Serial.println(" templates into sensor");
    return loaded > 0;
}

// Upload a single template received from desktop app (via WiFi or BLE)
bool receiveAndStoreTemplate(int classId, int studentId, const String& name,
                             const uint8_t* data, int dataLen) {
    // Save to SD cache
    if (sdCache.isReady()) {
        sdCache.saveTemplate(classId, studentId, data, dataLen);
    }
    
    // Update roster
    studentRoster[String(studentId)] = name;
    
    Serial.print("[TPL] Received template for student ");
    Serial.print(studentId);
    Serial.print(" (");
    Serial.print(dataLen);
    Serial.println(" bytes)");
    return true;
}

// ─── Enrollment (Register) ──────────────────────────────────
void enrollTask(void* param) {
    uint16_t id = registerTargetId;
    String name = registerTargetName;
    int classId = loadedClassId >= 0 ? loadedClassId : 0;
    
    setRegisterState("starting", name + " | " + String(id));
    
    // Delete existing slot
    fp.deleteTemplate(id);
    delay(100);
    
    // First scan
    setRegisterState("waiting_1st", name);
    displayMessage("Place Finger", "1st scan");
    if (!fp.waitForFinger(15000)) {
        setRegisterState("failed", "No finger detected");
        displayMessage("Scan Failed");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    delay(300);
    if (!fp.img2Tz(1)) {
        setRegisterState("failed", "Feature extraction failed");
        displayMessage("Feature Fail");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    setRegisterState("captured_1st", name);
    
    // Check for duplicates
    int dupId = fp.search(1, 0, 255);
    if (dupId >= 0 && dupId != id) {
        setRegisterState("failed", "Duplicate: ID " + String(dupId));
        displayMessage("Duplicate!", "ID " + String(dupId));
        holdDisplayFor(2500);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    // Remove finger
    setRegisterState("remove_finger", name);
    displayMessage("Remove Finger");
    if (!fp.waitForRemoval(10000)) {
        setRegisterState("failed", "Remove timeout");
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    delay(500);
    
    // Second scan
    setRegisterState("waiting_2nd", name);
    displayMessage("Place Again", "2nd scan");
    if (!fp.waitForFinger(15000)) {
        setRegisterState("failed", "No finger on 2nd scan");
        displayMessage("Scan Failed");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    delay(300);
    if (!fp.img2Tz(2)) {
        setRegisterState("failed", "Feature extraction failed (2nd)");
        displayMessage("Feature Fail");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    setRegisterState("captured_2nd", name);

    // Create model
    setRegisterState("creating_model", name);
    displayMessage("Creating Model");
    bool modelOk = false;
    for (int i = 0; i < 3; i++) {
        if (fp.regModel()) { modelOk = true; break; }
        delay(300);
    }
    if (!modelOk) {
        setRegisterState("failed", "Model creation failed");
        displayMessage("Model Failed");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    // Store in sensor
    setRegisterState("saving_model", name);
    displayMessage("Saving...", String(id));
    bool storeOk = false;
    for (int i = 0; i < 3; i++) {
        if (fp.store(1, id)) { storeOk = true; break; }
        delay(300);
    }
    if (!storeOk) {
        setRegisterState("failed", "Store failed");
        displayMessage("Save Failed");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    // Extract template and save to SD
    setRegisterState("extracting", name);
    int tplLen = extractAndSaveTemplate(id, classId, id);
    
    // Update roster AND slot mapping
    studentRoster[String(id)] = name;
    if (id < MAX_CLASS_SIZE) {
        slotToStudent[id] = id;
        slotToName[id] = name;
    }
    
    // Success
    setRegisterState("success", name + " | " + String(id));
    displayMessage("Registered!", name.substring(0, 12));
    holdDisplayFor(2500);
    
    // Notify BLE
    DynamicJsonDocument doc(512);
    doc["event"] = "register_complete";
    doc["status"] = "success";
    doc["student_id"] = id;
    doc["name"] = name;
    doc["template_size"] = tplLen;
    String json;
    serializeJson(doc, json);
    bleNotifyStatus(json);
    
    registerTaskHandle = nullptr;
    vTaskDelete(nullptr);
}

// ─── Attendance Matching ────────────────────────────────────
int matchFingerprint() {
    if (!fp.waitForFinger(8000)) return -1;
    
    delay(300);
    bool ok = false;
    for (int i = 0; i < 3; i++) {
        if (fp.img2Tz(1)) { ok = true; break; }
        delay(250);
    }
    if (!ok) return -1;
    
    delay(200);
    int slotId = fp.search(1, 0, (uint16_t)loadedStudentCount);
    if (slotId < 0) {
        // Retry once
        delay(150);
        slotId = fp.search(1, 0, 255);
    }
    return slotId;
}

// ─── Unified Command Processor ──────────────────────────────
// Both WiFi (HTTP) and BLE feed commands here
void processCommand(const String& jsonCmd, String& response) {
    DynamicJsonDocument doc(2048);
    DeserializationError err = deserializeJson(doc, jsonCmd);
    DynamicJsonDocument resp(1024);
    
    if (err) {
        resp["status"] = "error";
        resp["message"] = "Invalid JSON";
        serializeJson(resp, response);
        return;
    }
    
    String cmd = doc["cmd"].as<String>();
    
    if (cmd == "status") {
        resp["status"] = "success";
        resp["sta_connected"] = sta_connected;
        resp["sta_ip"] = sta_connected ? WiFi.localIP().toString() : "";
        resp["ap_ip"] = WiFi.softAPIP().toString();
        resp["ble_connected"] = bleClientConnected;
        resp["loaded_class"] = loadedClassId;
        resp["loaded_students"] = loadedStudentCount;
        resp["sd_ready"] = sdCache.isReady();
        resp["attendance_mode"] = attendance_mode;
        resp["wifi_ssid"] = config_manager.getWiFiSSID();
    }
    else if (cmd == "register") {
        uint16_t id = doc["id"] | 0;
        String name = doc["name"] | "Student";
        int classId = doc["class_id"] | (loadedClassId >= 0 ? loadedClassId : 0);
        
        if (id == 0) {
            resp["status"] = "error";
            resp["message"] = "Missing id";
        } else if (isRegisterBusy()) {
            resp["status"] = "error";
            resp["message"] = "Registration already running";
        } else {
            registerTargetId = id;
            registerTargetName = name;
            loadedClassId = classId;
            xTaskCreatePinnedToCore(enrollTask, "enroll", 8192, nullptr, 1, &registerTaskHandle, 0);
            resp["status"] = "started";
            resp["student_id"] = id;
        }
    }
    else if (cmd == "register_status") {
        resp["status"] = "success";
        resp["state"] = registerState;
        resp["detail"] = registerDetail;
        resp["id"] = registerTargetId;
        resp["name"] = registerTargetName;
    }
    else if (cmd == "load_class") {
        int classId = doc["class_id"] | -1;
        if (classId < 0) {
            resp["status"] = "error";
            resp["message"] = "Missing class_id";
        } else {
            // Load student names into roster
            if (doc.containsKey("students")) {
                JsonArray students = doc["students"].as<JsonArray>();
                for (int i = 0; i < (int)students.size() && i < MAX_CLASS_SIZE; i++) {
                    int sid = students[i]["id"] | 0;
                    String sname = students[i]["name"] | "Unknown";
                    slotToName[i] = sname;
                    studentRoster[String(sid)] = sname;
                }
            }
            bool ok = loadClassTemplates(classId);
            resp["status"] = ok ? "success" : "error";
            resp["loaded"] = loadedStudentCount;
            resp["class_id"] = classId;
        }
    }
    else if (cmd == "load_class_from_sd") {
        int classId = doc["class_id"] | -1;
        if (classId < 0) {
            resp["status"] = "error";
            resp["message"] = "Missing class_id";
        } else {
            bool ok = loadClassTemplates(classId);
            resp["status"] = ok ? "success" : "error";
            resp["loaded"] = loadedStudentCount;
        }
    }

    else if (cmd == "upload_template") {
        // Receive a single template from desktop app
        int studentId = doc["student_id"] | 0;
        int classId = doc["class_id"] | (loadedClassId >= 0 ? loadedClassId : 0);
        String name = doc["name"] | "Student";
        String b64data = doc["template"] | "";
        
        if (studentId == 0 || b64data.length() == 0) {
            resp["status"] = "error";
            resp["message"] = "Missing student_id or template data";
        } else {
            // Decode base64 template
            int decodedLen = b64data.length() * 3 / 4;
            uint8_t* decoded = (uint8_t*)malloc(decodedLen);
            if (decoded) {
                // Simple base64 decode
                int actualLen = 0;
                const char* b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
                const char* src = b64data.c_str();
                int srcLen = b64data.length();
                
                for (int i = 0; i < srcLen; i += 4) {
                    uint32_t sextet[4] = {0, 0, 0, 0};
                    for (int j = 0; j < 4 && (i + j) < srcLen; j++) {
                        char c = src[i + j];
                        if (c == '=') { sextet[j] = 0; }
                        else {
                            const char* p = strchr(b64chars, c);
                            sextet[j] = p ? (p - b64chars) : 0;
                        }
                    }
                    uint32_t triple = (sextet[0] << 18) | (sextet[1] << 12) | (sextet[2] << 6) | sextet[3];
                    if (actualLen < decodedLen) decoded[actualLen++] = (triple >> 16) & 0xFF;
                    if (actualLen < decodedLen && src[i+2] != '=') decoded[actualLen++] = (triple >> 8) & 0xFF;
                    if (actualLen < decodedLen && src[i+3] != '=') decoded[actualLen++] = triple & 0xFF;
                }
                
                receiveAndStoreTemplate(classId, studentId, name, decoded, actualLen);
                free(decoded);
                resp["status"] = "success";
                resp["student_id"] = studentId;
                resp["bytes"] = actualLen;
            } else {
                resp["status"] = "error";
                resp["message"] = "Memory allocation failed";
            }
        }
    }
    else if (cmd == "start_attendance") {
        if (!attendance_mode) {
            // Only clear buffer when first starting (not on repeat calls)
            attendance.clear();
        }
        attendance_mode = true;
        attendanceFeedbackUntilMs = 0;
        attendancePromptVisible = false;
        displayAttendancePrompt();
        resp["status"] = "success";
        resp["class_id"] = loadedClassId;
        resp["students"] = loadedStudentCount;
        resp["message"] = "Attendance started";
    }
    else if (cmd == "stop_attendance") {
        attendance_mode = false;
        displayMessage("Attendance", "Stopped");
        holdDisplayFor(1500);
        resp["status"] = "success";
    }
    else if (cmd == "attendance") {
        // Manual trigger: try to match a finger now
        int slotId = matchFingerprint();
        if (slotId >= 0 && slotId < MAX_CLASS_SIZE) {
            int studentId = slotToStudent[slotId];
            String name = slotToName[slotId];
            if (name.length() == 0) name = studentRoster[String(studentId)] | "Unknown";
            
            // Record
            JsonObject rec = attendance.createNestedObject();
            rec["id"] = studentId;
            rec["slot"] = slotId;
            rec["name"] = name;
            rec["time"] = String(millis());
            
            displayAttendanceResult(true, name, studentId);
            fp.waitForRemoval(2000);
            
            resp["status"] = "success";
            resp["student_id"] = studentId;
            resp["name"] = name;
            resp["message"] = "Attendance marked for " + name + " (ID: " + String(studentId) + ")";
        } else {
            displayAttendanceResult(false, "", 0);
            resp["status"] = "error";
            resp["message"] = "No match found";
        }
    }

    else if (cmd == "get_attendance") {
        String json;
        serializeJson(attendance, json);
        response = json;
        return;
    }
    else if (cmd == "clear_attendance") {
        attendance.clear();
        resp["status"] = "success";
    }
    else if (cmd == "delete_template") {
        uint16_t id = doc["id"] | 0;
        int classId = doc["class_id"] | (loadedClassId >= 0 ? loadedClassId : 0);
        fp.deleteTemplate(id);
        if (sdCache.isReady()) sdCache.deleteTemplate(classId, id);
        studentRoster.remove(String(id));
        resp["status"] = "success";
    }
    else if (cmd == "set_wifi") {
        String ssid = doc["ssid"] | "";
        String pass = doc["password"] | "";
        String ip = doc["static_ip"] | "";
        if (ssid.length() > 0) {
            config_manager.setWiFiCredentials(ssid, pass);
            if (ip.length() > 0) config_manager.set("static_ip", ip);
            resp["status"] = "success";
            resp["message"] = "WiFi config saved. Restart to apply.";
        } else {
            resp["status"] = "error";
            resp["message"] = "Missing ssid";
        }
    }
    else if (cmd == "get_template") {
        // Download template from sensor after registration
        uint16_t id = doc["id"] | 0;
        if (id == 0) {
            resp["status"] = "error";
            resp["message"] = "Missing id";
        } else {
            if (!fp.loadChar(1, id)) {
                resp["status"] = "error";
                resp["message"] = "Template not in sensor";
            } else {
                uint8_t tplData[1024];
                int tplLen = fp.uploadTemplate(1, tplData, sizeof(tplData));
                if (tplLen > 0) {
                    // Base64 encode
                    const char* b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
                    String b64 = "";
                    for (int i = 0; i < tplLen; i += 3) {
                        uint32_t n = ((uint32_t)tplData[i] << 16);
                        if (i + 1 < tplLen) n |= ((uint32_t)tplData[i+1] << 8);
                        if (i + 2 < tplLen) n |= tplData[i+2];
                        b64 += b64chars[(n >> 18) & 0x3F];
                        b64 += b64chars[(n >> 12) & 0x3F];
                        b64 += (i + 1 < tplLen) ? b64chars[(n >> 6) & 0x3F] : '=';
                        b64 += (i + 2 < tplLen) ? b64chars[n & 0x3F] : '=';
                    }
                    resp["status"] = "success";
                    resp["template"] = b64;
                    resp["size"] = tplLen;
                } else {
                    resp["status"] = "error";
                    resp["message"] = "Upload from sensor failed";
                }
            }
        }
    }
    else if (cmd == "sd_info") {
        resp["status"] = "success";
        resp["ready"] = sdCache.isReady();
        resp["total_mb"] = (int)(sdCache.getTotalBytes() / (1024 * 1024));
        resp["used_mb"] = (int)(sdCache.getUsedBytes() / (1024 * 1024));
    }
    else {
        resp["status"] = "error";
        resp["message"] = "Unknown command: " + cmd;
    }
    
    serializeJson(resp, response);
}

// ─── BLE Template Transfer Callback ─────────────────────────
void TemplateCharCallbacks::onWrite(NimBLECharacteristic* pChar) {
    std::string val = pChar->getValue();
    if (val.length() < 5) return;  // Minimum: 2 id + 1 chunk + 1 total + 1 data
    
    const uint8_t* raw = (const uint8_t*)val.data();
    uint16_t studentId = ((uint16_t)raw[0] << 8) | raw[1];
    uint8_t chunkNum = raw[2];
    uint8_t totalChunks = raw[3];
    int dataLen = val.length() - 4;
    
    if (chunkNum == 0) {
        // Start new transfer
        bleTemplateTransfer.studentId = studentId;
        bleTemplateTransfer.receivedBytes = 0;
        bleTemplateTransfer.inProgress = true;
        memset(bleTemplateTransfer.data, 0, sizeof(bleTemplateTransfer.data));
    }
    
    // Append data
    if (bleTemplateTransfer.receivedBytes + dataLen <= (int)sizeof(bleTemplateTransfer.data)) {
        memcpy(bleTemplateTransfer.data + bleTemplateTransfer.receivedBytes, raw + 4, dataLen);
        bleTemplateTransfer.receivedBytes += dataLen;
    }
    
    // Last chunk?
    if (chunkNum + 1 >= totalChunks) {
        int classId = loadedClassId >= 0 ? loadedClassId : 0;
        receiveAndStoreTemplate(classId, studentId, String(studentId),
                               bleTemplateTransfer.data, bleTemplateTransfer.receivedBytes);
        bleTemplateTransfer.inProgress = false;
        
        // Notify completion
        String resp = "{\"event\":\"template_received\",\"student_id\":" + String(studentId) +
                      ",\"bytes\":" + String(bleTemplateTransfer.receivedBytes) + "}";
        bleNotifyStatus(resp);
        Serial.print("[BLE] Template transfer complete for student ");
        Serial.println(studentId);
    }
}

// ─── HTTP Handlers (wrap processCommand) ────────────────────
void handleCommand(AsyncWebServerRequest* request, uint8_t* data, size_t len, size_t index, size_t total) {
    String body = String((char*)data).substring(0, len);
    String response;
    processCommand(body, response);
    request->send(200, "application/json", response);
}

// Legacy HTTP endpoints that wrap into the unified command system
void setupLegacyRoutes() {
    // POST /command - unified JSON command endpoint
    server.on("/command", HTTP_POST, [](AsyncWebServerRequest* req){},
              NULL, handleCommand);
    
    // Legacy GET endpoints for backward compatibility
    server.on("/status", HTTP_GET, [](AsyncWebServerRequest* req) {
        String resp;
        processCommand("{\"cmd\":\"status\"}", resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/register", HTTP_GET, [](AsyncWebServerRequest* req) {
        DynamicJsonDocument doc(256);
        doc["cmd"] = "register";
        if (req->hasParam("id")) doc["id"] = req->getParam("id")->value().toInt();
        if (req->hasParam("name")) doc["name"] = req->getParam("name")->value();
        if (req->hasParam("class_id")) doc["class_id"] = req->getParam("class_id")->value().toInt();
        String json, resp;
        serializeJson(doc, json);
        processCommand(json, resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/register_status", HTTP_GET, [](AsyncWebServerRequest* req) {
        String resp;
        processCommand("{\"cmd\":\"register_status\"}", resp);
        req->send(200, "application/json", resp);
    });

    server.on("/attendance", HTTP_GET, [](AsyncWebServerRequest* req) {
        // Return the last attendance mark (for backward-compat with Python app polling)
        // Include count so the app can detect new marks vs stale data
        static size_t lastReportedCount = 0;
        if (attendance.size() > 0 && attendance.size() != lastReportedCount) {
            lastReportedCount = attendance.size();
            JsonObject last = attendance[attendance.size() - 1];
            int sid = last["id"] | 0;
            String name = last["name"] | "Unknown";
            String msg = "Attendance marked for " + name + " (ID: " + String(sid) + ")";
            req->send(200, "text/plain", msg);
        } else {
            req->send(200, "text/plain", "Waiting for fingerprint");
        }
    });
    
    server.on("/get_attendance", HTTP_GET, [](AsyncWebServerRequest* req) {
        String resp;
        processCommand("{\"cmd\":\"get_attendance\"}", resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/clear_attendance", HTTP_GET, [](AsyncWebServerRequest* req) {
        String resp;
        processCommand("{\"cmd\":\"clear_attendance\"}", resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/start_attendance", HTTP_GET, [](AsyncWebServerRequest* req) {
        String resp;
        processCommand("{\"cmd\":\"start_attendance\"}", resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/stop_attendance", HTTP_GET, [](AsyncWebServerRequest* req) {
        String resp;
        processCommand("{\"cmd\":\"stop_attendance\"}", resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/delete", HTTP_GET, [](AsyncWebServerRequest* req) {
        DynamicJsonDocument doc(128);
        doc["cmd"] = "delete_template";
        if (req->hasParam("id")) doc["id"] = req->getParam("id")->value().toInt();
        String json, resp;
        serializeJson(doc, json);
        processCommand(json, resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/load_class", HTTP_GET, [](AsyncWebServerRequest* req) {
        DynamicJsonDocument doc(128);
        doc["cmd"] = "load_class_from_sd";
        if (req->hasParam("class_id")) doc["class_id"] = req->getParam("class_id")->value().toInt();
        String json, resp;
        serializeJson(doc, json);
        processCommand(json, resp);
        req->send(200, "application/json", resp);
    });
    
    server.on("/get_template", HTTP_GET, [](AsyncWebServerRequest* req) {
        DynamicJsonDocument doc(128);
        doc["cmd"] = "get_template";
        if (req->hasParam("id")) doc["id"] = req->getParam("id")->value().toInt();
        String json, resp;
        serializeJson(doc, json);
        processCommand(json, resp);
        req->send(200, "application/json", resp);
    });
}

// ─── Setup ──────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    // Initialize slot mapping
    for (int i = 0; i < MAX_CLASS_SIZE; i++) {
        slotToStudent[i] = -1;
        slotToName[i] = "";
    }
    
    // OLED
    Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
    if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
        Serial.println("[OLED] Init failed");
    } else {
        displayMessage("GWASOAT", "Starting...");
    }
    delay(500);
    
    // SPIFFS
    if (!SPIFFS.begin(true)) {
        Serial.println("[SPIFFS] Mount failed");
    }
    
    // Config
    config_manager.loadConfig();
    
    // Load roster from SPIFFS
    File rosterFile = SPIFFS.open("/students.json", "r");
    if (rosterFile) {
        deserializeJson(studentRoster, rosterFile);
        rosterFile.close();
    }
    
    // Fingerprint sensor
    fp.begin(FP_BAUD_RATE, PIN_FP_RX, PIN_FP_TX);
    Serial.println("[FP] Sensor initialized");
    
    // SD Card
    displayMessage("Init SD Card");
    if (sdCache.begin()) {
        Serial.println("[SD] Ready");
    } else {
        Serial.println("[SD] Failed - continuing without SD");
    }
    
    // WiFi (AP + STA)
    displayMessage("Connecting WiFi");
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.print("[WIFI] AP IP: ");
    Serial.println(WiFi.softAPIP());
    
    String staticIPStr = config_manager.getStaticIP();
    String gatewayStr = config_manager.getGateway();
    String subnetStr = config_manager.getSubnet();
    IPAddress staticIP, gatewayIP, subnetIP;
    staticIP.fromString(staticIPStr);
    gatewayIP.fromString(gatewayStr);
    subnetIP.fromString(subnetStr);
    WiFi.config(staticIP, gatewayIP, subnetIP);
    
    String ssid = config_manager.getWiFiSSID();
    String password = config_manager.getWiFiPassword();
    WiFi.begin(ssid.c_str(), password.c_str());
    
    unsigned long wifiStart = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 12000) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    
    sta_connected = (WiFi.status() == WL_CONNECTED);
    if (sta_connected) {
        Serial.print("[WIFI] STA IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("[WIFI] STA failed, AP only");
    }

    // BLE
    initBLE("GWASOAT-Device");
    
    // HTTP Server
    setupLegacyRoutes();
    server.begin();
    Serial.println("[HTTP] Server started");
    
    displayIdleStatus();
    Serial.println("=== GWASOAT System Ready ===");
}

// ─── Main Loop ──────────────────────────────────────────────
void loop() {
    // WiFi auto-reconnect check (every 30 seconds)
    static unsigned long lastWifiCheck = 0;
    if (millis() - lastWifiCheck > 30000) {
        lastWifiCheck = millis();
        if (WiFi.status() != WL_CONNECTED) {
            sta_connected = false;
            Serial.println("[WIFI] Disconnected, reconnecting...");
            WiFi.reconnect();
            unsigned long reconStart = millis();
            while (WiFi.status() != WL_CONNECTED && millis() - reconStart < 5000) {
                delay(250);
            }
            if (WiFi.status() == WL_CONNECTED) {
                sta_connected = true;
                Serial.print("[WIFI] Reconnected: ");
                Serial.println(WiFi.localIP());
            }
        } else {
            sta_connected = true;
        }
    }

    // Respect display hold (but DON'T skip attendance scanning)
    bool displayHeld = (millis() < displayHoldUntilMs);
    
    // Don't interfere during registration
    if (isRegisterBusy()) {
        delay(10);
        return;
    }
    
    // Attendance mode: continuously scan for fingers
    if (attendance_mode) {
        // Update display only when not held
        if (!displayHeld && millis() > attendanceFeedbackUntilMs && !attendancePromptVisible) {
            displayAttendancePrompt();
        }
        
        // Always try to detect a finger (non-blocking single check)
        if (millis() > attendanceFeedbackUntilMs) {
            if (fp.getImage()) {
                delay(200);
                if (fp.img2Tz(1)) {
                    int slotId = fp.search(1, 0, (uint16_t)(loadedStudentCount > 0 ? loadedStudentCount : 255));
                    if (slotId < 0) {
                        delay(100);
                        slotId = fp.search(1, 0, 255);
                    }
                    
                    if (slotId >= 0 && slotId < MAX_CLASS_SIZE) {
                        int studentId = slotToStudent[slotId];
                        // If no class was loaded, slot ID = student ID (direct registration)
                        if (studentId < 0) studentId = slotId;
                        String name = slotToName[slotId];
                        if (name.length() == 0) {
                            String key = String(studentId);
                            if (studentRoster.containsKey(key)) {
                                name = studentRoster[key].as<String>();
                            } else {
                                name = "ID:" + String(studentId);
                            }
                        }
                        
                        // Check if already marked this session
                        bool alreadyMarked = false;
                        for (size_t i = 0; i < attendance.size(); i++) {
                            if (attendance[i]["id"] == studentId) {
                                alreadyMarked = true;
                                break;
                            }
                        }
                        
                        if (!alreadyMarked) {
                            JsonObject rec = attendance.createNestedObject();
                            rec["id"] = studentId;
                            rec["slot"] = slotId;
                            rec["name"] = name;
                            rec["time"] = String(millis());
                            
                            // Log to SD
                            if (sdCache.isReady()) {
                                sdCache.logAttendance(loadedClassId, 0, studentId, name, String(millis()));
                            }
                            
                            // Notify BLE
                            DynamicJsonDocument ev(256);
                            ev["event"] = "attendance_marked";
                            ev["student_id"] = studentId;
                            ev["name"] = name;
                            String evJson;
                            serializeJson(ev, evJson);
                            bleNotifyStatus(evJson);
                            
                            Serial.print("[ATT] Marked: ");
                            Serial.print(name);
                            Serial.print(" (ID:");
                            Serial.print(studentId);
                            Serial.println(")");
                            
                            displayAttendanceResult(true, name, studentId);
                        } else {
                            displayMessage("Already Marked", name.substring(0, 10));
                            holdDisplayFor(1200);
                        }
                        
                        // Wait briefly for finger removal, then continue regardless
                        unsigned long rmStart = millis();
                        while (millis() - rmStart < 1500) {
                            if (!fp.getImage()) break;  // Finger removed
                            delay(100);
                        }
                        // Extra pause to let display show before going back to prompt
                        delay(500);
                        attendancePromptVisible = false;
                    } else {
                        displayAttendanceResult(false, "", 0);
                        delay(1500);
                        attendancePromptVisible = false;
                    }
                }
            }
        }
        
        delay(50);  // Small delay between scan attempts
    } else {
        // Idle display rotation
        if (!displayHeld && (!idleStatusVisible || millis() - lastIdleRefreshMs > 4000)) {
            displayIdleStatus();
        }
        delay(100);
    }
}
