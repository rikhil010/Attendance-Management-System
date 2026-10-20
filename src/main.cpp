#include <Arduino.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include "pins.h"
#include "config.h"
#include "fingerprint.h"
#include "tft_display.h"

// ─── Hardware Objects ───────────────────────────────────────
HardwareSerial fingerSerial(2);
FingerprintSensor fp(fingerSerial);
TftDisplay display;
AsyncWebServer server(80);
ConfigManager config_manager;

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

// Class loading state
int loadedClassId = -1;
int loadedStudentCount = 0;
String loadedClassName = "";

// Last registered template (extracted after regModel, before store)
uint8_t lastTemplate[2048];
int lastTemplateLen = 0;
uint16_t lastTemplateId = 0;

// Slot-to-student mapping (sensor slot → real student ID)
#define MAX_CLASS_SIZE 255
int slotToStudent[MAX_CLASS_SIZE];
String slotToName[MAX_CLASS_SIZE];

// Attendance buffer
DynamicJsonDocument attendance(4096);
DynamicJsonDocument studentRoster(4096);

// Save roster to SPIFFS
void saveStudentRoster() {
    File file = SPIFFS.open("/students.json", "w");
    if (file) {
        serializeJson(studentRoster, file);
        file.close();
    }
}

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
    display.setCursor(0, 14);
    display.println("WiFi: " + config_manager.getWiFiSSID());
    display.setCursor(0, 28);
    if (sta_connected && WiFi.status() == WL_CONNECTED) {
        display.println("IP: " + WiFi.localIP().toString());
    } else {
        display.println("Hotspot: 192.168.4.1");
    }
    display.setCursor(0, 42);
    if (loadedClassName.length() > 0) {
        display.println("Class: " + loadedClassName);
    } else if (loadedClassId >= 0) {
        display.println("Class: " + String(loadedClassId) + " | " + String(loadedStudentCount) + " students");
    } else {
        display.println("No class loaded");
    }
    display.setCursor(0, 54);
    display.println("Ready");
    display.display();
    idleStatusVisible = true;
    attendancePromptVisible = false;
    lastIdleRefreshMs = millis();
}

void displayAttendancePrompt() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    if (loadedClassName.length() > 0) {
        display.println("Class: " + loadedClassName);
    } else if (loadedClassId >= 0) {
        display.println("Class ID: " + String(loadedClassId));
    } else {
        display.println("Attendance Mode");
    }
    display.setCursor(0, 16);
    display.println("Place finger to");
    display.setCursor(0, 28);
    display.println("mark attendance");
    display.setCursor(0, 46);
    display.println(String(loadedStudentCount) + " students loaded");
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
    attendanceFeedbackUntilMs = millis() + (success ? 1500 : 800);
    holdDisplayFor(success ? 1500 : 800);
    attendancePromptVisible = false;
    idleStatusVisible = false;
}

// ─── Register State ─────────────────────────────────────────
void setRegisterState(const String& state, const String& detail = "") {
    registerState = state;
    registerDetail = detail;
    Serial.println("[REG] " + state + " | " + detail);
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
    
    // Save to SD card (disabled - SD removed)
    
    Serial.print("[TPL] Extracted and saved template, ");
    Serial.print(tplLen);
    Serial.println(" bytes");
    return tplLen;
}

// Upload a single template received from desktop app (via WiFi or BLE)
bool receiveAndStoreTemplate(int classId, int studentId, const String& name,
                             const uint8_t* data, int dataLen) {
    Serial.print("[TPL] Receiving template for student ");
    Serial.print(studentId);
    Serial.print(" (");
    Serial.print(dataLen);
    Serial.println(" bytes)");
    
    // OLED: show receiving
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Loading Class...");
    display.setCursor(0, 18);
    display.println("Received:");
    display.setCursor(0, 32);
    display.println(name.substring(0, 16));
    display.setCursor(0, 50);
    display.println("Slot " + String(studentId));
    display.display();
    
    // ─── STEP A: DownChar - stream template into Character Buffer 1 ───
    bool stepA = fp.downloadTemplate(1, data, dataLen);
    if (!stepA) {
        Serial.println("[TPL] Step A (DownChar) failed - not storing");
        return false;
    }
    delay(150);
    
    // ─── STEP B: Store buffer 1 to flash slot - ONLY if Step A succeeded ───
    delay(500);  // Sensor needs time to process 1940 bytes received via DnChar
    bool stepB = false;
    for (int i = 0; i < 5; i++) {
        if (fp.store(1, (uint16_t)studentId)) { stepB = true; break; }
        delay(500);
    }
    if (!stepB) {
        Serial.println("[TPL] Step B (store) failed after 5 attempts");
        return false;
    }
    
    Serial.print("[TPL] Stored at slot ");
    Serial.println(studentId);
    if (studentId < MAX_CLASS_SIZE) {
        slotToStudent[studentId] = studentId;
        slotToName[studentId] = name;
        loadedStudentCount++;
    }
    studentRoster[String(studentId)] = name;
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
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Register: " + name.substring(0, 12));
    display.setCursor(0, 18);
    display.setTextSize(2);
    display.println("PLACE");
    display.println("FINGER");
    display.display();
    if (!fp.waitForFinger(15000)) {
        setRegisterState("failed", "No finger detected");
        displayMessage("Scan Failed");
        holdDisplayFor(2000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    // Confirm finger is still there and get a good image
    delay(800);
    if (!fp.getImage()) {
        delay(500);
        if (!fp.getImage()) {
            setRegisterState("failed", "Lost finger contact");
            displayMessage("Hold Finger", "Steady!");
            holdDisplayFor(2000);
            registerTaskHandle = nullptr;
            vTaskDelete(nullptr);
            return;
        }
    }
    
    delay(200);
    bool feat1 = false;
    for (int attempt = 0; attempt < 5; attempt++) {
        Serial.print("[REG] img2Tz(1) attempt ");
        Serial.println(attempt + 1);
        if (fp.img2Tz(1)) { feat1 = true; break; }
        // Re-capture image and try again
        delay(300);
        fp.getImage();
        delay(300);
    }
    if (!feat1) {
        setRegisterState("failed", "Feature extraction failed");
        displayMessage("Feature Fail", "Press harder");
        holdDisplayFor(2500);
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
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Register: " + name.substring(0, 12));
    display.setCursor(0, 18);
    display.setTextSize(2);
    display.println("REMOVE");
    display.println("FINGER");
    display.display();
    if (!fp.waitForRemoval(10000)) {
        setRegisterState("failed", "Remove timeout");
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    delay(500);
    
    // Second scan - retry full capture+convert cycle for reliability
    setRegisterState("waiting_2nd", name);
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Register: " + name.substring(0, 12));
    display.setCursor(0, 18);
    display.setTextSize(2);
    display.println("PLACE");
    display.println("AGAIN");
    display.display();

    bool feat2 = false;
    unsigned long scan2Start = millis();
    while (millis() - scan2Start < 20000 && !feat2) {  // 20s window
        // Wait for a finger
        if (!fp.getImage()) {
            delay(100);
            continue;
        }
        // Finger detected - hold and capture a clean image, then convert
        delay(400);
        for (int attempt = 0; attempt < 3; attempt++) {
            if (!fp.getImage()) break;  // finger lifted
            delay(150);
            Serial.print("[REG] img2Tz(2) attempt ");
            Serial.println(attempt + 1);
            if (fp.img2Tz(2)) { feat2 = true; break; }
            delay(250);
        }
        if (!feat2) {
            // Failed this cycle - prompt to lift and retry
            display.clearDisplay();
            display.setTextColor(SSD1306_WHITE);
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println("Hold steady!");
            display.setCursor(0, 18);
            display.setTextSize(2);
            display.println("PRESS");
            display.println("FIRMLY");
            display.display();
            fp.waitForRemoval(3000);
            delay(300);
            display.clearDisplay();
            display.setTextColor(SSD1306_WHITE);
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println("Register: " + name.substring(0, 12));
            display.setCursor(0, 18);
            display.setTextSize(2);
            display.println("PLACE");
            display.println("AGAIN");
            display.display();
        }
    }

    if (!feat2) {
        setRegisterState("failed", "Feature extraction failed (2nd)");
        displayMessage("Scan Failed", "Try again");
        holdDisplayFor(2500);
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
    
    // Store in sensor FIRST (clean - no UpChar before it to leave garbage)
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
    
    // Extract template from buffer 1 (model still in buffer 1 after store)
    delay(300);
    lastTemplateLen = fp.uploadTemplate(1, lastTemplate, sizeof(lastTemplate));
    lastTemplateId = id;
    if (lastTemplateLen < 0) {
        // No clean end packet - retry once
        delay(200);
        lastTemplateLen = fp.uploadTemplate(1, lastTemplate, sizeof(lastTemplate));
    }
    if (lastTemplateLen < 0) lastTemplateLen = 0;  // mark invalid
    Serial.print("[REG] Extracted template: ");
    Serial.print(lastTemplateLen);
    Serial.println(" bytes");
    delay(200);
    
    // ─── VERIFICATION STEP: Test if fingerprint matches ─────
    setRegisterState("testing", name);
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("TEST FINGERPRINT");
    display.setCursor(0, 16);
    display.println(name.substring(0, 14));
    display.setCursor(0, 34);
    display.setTextSize(2);
    display.println("PLACE");
    display.println("FINGER");
    display.display();
    
    // Wait for finger removal first (in case still touching from registration)
    fp.waitForRemoval(3000);
    delay(500);
    
    bool testPassed = false;
    unsigned long testStart = millis();
    
    while (millis() - testStart < 15000) {  // 15 second timeout
        if (fp.getImage()) {
            delay(300);
            if (fp.img2Tz(1)) {
                int matchId = fp.search(1, 0, 255);
                if (matchId == id) {
                    testPassed = true;
                    break;
                } else {
                    // Wrong finger or no match
                    display.clearDisplay();
                    display.setTextColor(SSD1306_WHITE);
                    display.setTextSize(1);
                    display.setCursor(0, 0);
                    display.println("NOT MATCHED");
                    display.setCursor(0, 20);
                    display.println("Try again...");
                    display.display();
                    fp.waitForRemoval(2000);
                    delay(300);
                    // Show prompt again
                    display.clearDisplay();
                    display.setTextColor(SSD1306_WHITE);
                    display.setTextSize(1);
                    display.setCursor(0, 0);
                    display.println("TEST FINGERPRINT");
                    display.setCursor(0, 16);
                    display.println(name.substring(0, 14));
                    display.setCursor(0, 34);
                    display.setTextSize(2);
                    display.println("PLACE");
                    display.println("FINGER");
                    display.display();
                }
            }
        }
        delay(100);
    }
    
    if (!testPassed) {
        // Test failed - delete the template and fail registration
        fp.deleteTemplate(id);
        setRegisterState("failed", "Verification failed");
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);
        display.setTextSize(1);
        display.setCursor(0, 0);
        display.println("TEST FAILED");
        display.setCursor(0, 20);
        display.println("Registration");
        display.setCursor(0, 34);
        display.println("cancelled");
        display.display();
        holdDisplayFor(3000);
        registerTaskHandle = nullptr;
        vTaskDelete(nullptr);
        return;
    }
    
    // Test passed!
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("VERIFIED!");
    display.setCursor(0, 18);
    display.setTextSize(2);
    display.println("SUCCESS");
    display.display();
    delay(1500);
    fp.waitForRemoval(2000);
    
    // Template already extracted before store (lastTemplate buffer)
    // Update roster AND slot mapping
    studentRoster[String(id)] = name;
    saveStudentRoster();
    if (id < MAX_CLASS_SIZE) {
        slotToStudent[id] = id;
        slotToName[id] = name;
    }
    
    // Success
    setRegisterState("success", name + " | " + String(id));
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("REGISTERED!");
    display.setCursor(0, 16);
    display.println(name.substring(0, 16));
    display.setCursor(0, 34);
    display.println("Template sent");
    display.setCursor(0, 46);
    display.println("to laptop");
    display.display();
    holdDisplayFor(2500);
    
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
    DynamicJsonDocument doc(4096);
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

        resp["loaded_class"] = loadedClassId;
        resp["loaded_students"] = loadedStudentCount;
        resp["sd_ready"] = false;
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
            // Show registration mode immediately on OLED
            display.clearDisplay();
            display.setTextColor(SSD1306_WHITE);
            display.setTextSize(1);
            display.setCursor(0, 0);
            display.println("=== REGISTRATION ===");
            display.setCursor(0, 16);
            display.println("Student: " + name.substring(0, 14));
            display.setCursor(0, 30);
            display.println("ID: " + String(id));
            display.setCursor(0, 46);
            display.println("Starting...");
            display.display();
            
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
            // Clear sensor for new class
            fp.emptyDatabase();
            loadedStudentCount = 0;
            loadedClassId = classId;
            for (int i = 0; i < MAX_CLASS_SIZE; i++) {
                slotToStudent[i] = -1;
                slotToName[i] = "";
            }
            
            // Load student names into roster
            if (doc.containsKey("students")) {
                JsonArray students = doc["students"].as<JsonArray>();
                for (int i = 0; i < (int)students.size() && i < MAX_CLASS_SIZE; i++) {
                    int sid = students[i]["id"] | 0;
                    String sname = students[i]["name"] | "Unknown";
                    studentRoster[String(sid)] = sname;
                }
            }
            if (doc.containsKey("class_name")) {
                loadedClassName = doc["class_name"].as<String>();
            }
            resp["status"] = "success";
            resp["loaded"] = 0;
            resp["class_id"] = classId;
            resp["message"] = "Sensor cleared, ready for template uploads";
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
                
                bool ok = receiveAndStoreTemplate(classId, studentId, name, decoded, actualLen);
                free(decoded);
                resp["status"] = ok ? "success" : "error";
                resp["student_id"] = studentId;
                resp["bytes"] = actualLen;
                resp["loaded_count"] = loadedStudentCount;
                if (!ok) resp["message"] = "Failed to store template on sensor";
            } else {
                resp["status"] = "error";
                resp["message"] = "Memory allocation failed";
            }
        }
    }
    else if (cmd == "start_attendance") {
        if (!attendance_mode) {
            attendance.clear();
        }
        attendance_mode = true;
        if (doc.containsKey("class_name")) {
            loadedClassName = doc["class_name"].as<String>();
        }
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
        // Return last registered template - build response directly (large data)
        uint16_t id = doc["id"] | 0;
        const char* b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        
        uint8_t* tpl = nullptr;
        int tplLen = 0;
        static uint8_t tmpBuf[2048];
        
        if (id == 0) {
            response = "{\"status\":\"error\",\"message\":\"Missing id\"}";
            return;
        }
        
        if (lastTemplateLen > 0 && lastTemplateId == id) {
            tpl = lastTemplate;
            tplLen = lastTemplateLen;
        } else if (fp.loadChar(1, id)) {
            tplLen = fp.uploadTemplate(1, tmpBuf, sizeof(tmpBuf));
            if (tplLen > 0) tpl = tmpBuf;
        }
        
        if (tpl != nullptr && tplLen > 0) {
            // Build response with pre-allocated capacity to avoid fragmentation
            int b64Len = ((tplLen + 2) / 3) * 4;
            response.reserve(b64Len + 60);  // base64 + JSON wrapper
            response = "{\"status\":\"success\",\"size\":";
            response += String(tplLen);
            response += ",\"template\":\"";
            for (int i = 0; i < tplLen; i += 3) {
                uint32_t n = ((uint32_t)tpl[i] << 16);
                if (i + 1 < tplLen) n |= ((uint32_t)tpl[i+1] << 8);
                if (i + 2 < tplLen) n |= tpl[i+2];
                response += b64chars[(n >> 18) & 0x3F];
                response += b64chars[(n >> 12) & 0x3F];
                response += (i + 1 < tplLen) ? b64chars[(n >> 6) & 0x3F] : '=';
                response += (i + 2 < tplLen) ? b64chars[n & 0x3F] : '=';
            }
            response += "\"}";
            Serial.print("[FP] Served template for ID ");
            Serial.print(id);
            Serial.print(" (");
            Serial.print(tplLen);
            Serial.print(" bytes, resp len ");
            Serial.print(response.length());
            Serial.println(")");
        } else {
            response = "{\"status\":\"error\",\"message\":\"Template not available\"}";
        }
        return;
    }
    else if (cmd == "sd_info") {
        resp["status"] = "success";
        resp["ready"] = false;
        resp["total_mb"] = 0;
        resp["used_mb"] = 0;
    }
    else if (cmd == "clear_sensor") {
        // Wipe all fingerprint templates from sensor (cache cleared)
        bool ok = fp.emptyDatabase();
        loadedStudentCount = 0;
        loadedClassId = -1;
        loadedClassName = "";
        for (int i = 0; i < MAX_CLASS_SIZE; i++) {
            slotToStudent[i] = -1;
            slotToName[i] = "";
        }
        resp["status"] = ok ? "success" : "error";
        resp["message"] = ok ? "Sensor cleared" : "Failed to clear sensor";
        Serial.println("[FP] Sensor database cleared");
    }
    else {
        resp["status"] = "error";
        resp["message"] = "Unknown command: " + cmd;
    }
    
    serializeJson(resp, response);
}

// ─── HTTP Handlers (wrap processCommand) ────────────────────
void handleCommand(AsyncWebServerRequest* request, uint8_t* data, size_t len, size_t index, size_t total) {
    // Accumulate body across chunks (large template uploads span multiple calls)
    static String bodyBuf;
    if (index == 0) bodyBuf = "";
    for (size_t i = 0; i < len; i++) {
        bodyBuf += (char)data[i];
    }
    // Process only when full body received
    if (index + len >= total) {
        String response;
        processCommand(bodyBuf, response);
        request->send(200, "application/json", response);
        bodyBuf = "";
    }
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
        // Clear sensor and prepare for template uploads
        String resp;
        processCommand("{\"cmd\":\"clear_sensor\"}", resp);
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
    
    // TFT display (ILI9341, SPI)
    if (!display.begin()) {
        Serial.println("[TFT] Init failed");
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
    
    // WiFi - Start AP immediately (always available)
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    delay(100);  // Give AP time to start
    Serial.print("[WIFI] AP IP: ");
    Serial.println(WiFi.softAPIP());
    
    // HTTP Server - start NOW so hotspot is usable immediately
    setupLegacyRoutes();
    server.begin();
    Serial.println("[HTTP] Server started on AP");
    displayMessage("GWASOAT Ready", "AP: 192.168.4.1");
    
    // Now try to connect to router WiFi
    String ssid = config_manager.getWiFiSSID();
    String password = config_manager.getWiFiPassword();
    String staticIPStr = config_manager.getStaticIP();
    String gatewayStr = config_manager.getGateway();
    String subnetStr = config_manager.getSubnet();
    
    if (ssid.length() > 0) {
        IPAddress staticIP, gatewayIP, subnetIP;
        staticIP.fromString(staticIPStr);
        gatewayIP.fromString(gatewayStr);
        subnetIP.fromString(subnetStr);
        WiFi.config(staticIP, gatewayIP, subnetIP);
        WiFi.setSleep(false);
        WiFi.setAutoReconnect(true);
        WiFi.begin(ssid.c_str(), password.c_str());
        
        unsigned long wifiStart = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 8000) {
            delay(500);
            Serial.print(".");
        }
        Serial.println();
    }
    
    sta_connected = (WiFi.status() == WL_CONNECTED);
    if (sta_connected) {
        Serial.print("[WIFI] STA IP: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("[WIFI] STA failed, AP only");
    }
    


    
    displayIdleStatus();
    Serial.println("=== GWASOAT System Ready ===");
}

// ─── Main Loop ──────────────────────────────────────────────
void loop() {
    // WiFi auto-reconnect check (every 10 seconds)
    static unsigned long lastWifiCheck = 0;
    if (millis() - lastWifiCheck > 10000) {
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
        
        // ALWAYS scan for fingers (no gate - continuous scanning)
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
                            
                            Serial.print("[ATT] Marked: ");
                            Serial.print(name);
                            Serial.print(" (ID:");
                            Serial.print(studentId);
                            Serial.println(")");
                            
                            displayAttendanceResult(true, name, studentId);
                        } else {
                            displayMessage("Already Marked", name.substring(0, 10));
                            holdDisplayFor(600);
                        }
                        
                        // Wait briefly for finger removal, then continue regardless
                        unsigned long rmStart = millis();
                        while (millis() - rmStart < 1500) {
                            if (!fp.getImage()) break;  // Finger removed
                            delay(100);
                        }
                        // Brief pause then continue scanning
                        delay(200);
                        attendancePromptVisible = false;
                    } else {
                        displayAttendanceResult(false, "", 0);
                        delay(600);
                        attendancePromptVisible = false;
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
