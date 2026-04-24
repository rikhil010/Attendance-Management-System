#include <Arduino.h>
#include <HardwareSerial.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "../include/config.h"
#include "../include/ble_service.h"

HardwareSerial fingerSerial(2);

// OLED Display Setup
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define SDA_PIN 21
#define SCL_PIN 22
#define RXD2 16
#define TXD2 17
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

bool attendance_mode = false;

// Fallback AP credentials if router hotspot is unavailable
const char* AP_SSID = "Attendance-ESP32";
const char* AP_PASSWORD = "Attend1234";

// Global config manager
ConfigManager config_manager;

bool sta_connected = false;
String registerState = "idle";
String registerDetail = "";
uint16_t registerTargetId = 0;
String registerTargetName = "";
TaskHandle_t registerTaskHandle = nullptr;
unsigned long attendanceFeedbackUntilMs = 0;
unsigned long lastIdleRefreshMs = 0;
bool attendancePromptVisible = false;
bool idleStatusVisible = false;
bool showIdleWifiPage = true;
unsigned long displayHoldUntilMs = 0;

// Web server
AsyncWebServer server(80);

// Attendance data
DynamicJsonDocument attendance(1024);
DynamicJsonDocument studentRoster(4096);

bool getImage();

void holdDisplayFor(uint32_t durationMs) {
  displayHoldUntilMs = millis() + durationMs;
}

bool isRegisterBusy() {
  if (registerTaskHandle != nullptr) {
    return true;
  }
  return registerState != "idle" && registerState != "success" && registerState != "failed";
}

// Function to display OLED message
void displayMessage(String title, String message = "") {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(title);
  if (message.length() > 0) {
    display.setCursor(0, 20);
    display.setTextSize(2);
    display.println(message);
  }
  display.display();
}

void displayRegisterInfo(const String& name, uint16_t id) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Register Student");
  display.setCursor(0, 16);
  display.println("Name: " + name.substring(0, 16));
  display.setCursor(0, 32);
  display.println("ID: " + String(id));
  display.display();
  attendancePromptVisible = false;
  idleStatusVisible = false;
  holdDisplayFor(1200);
}

void displayIdleStatus() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("System Ready");
  if (showIdleWifiPage) {
    display.setCursor(0, 16);
    display.println("WiFi Name:");
    display.setCursor(0, 30);
    display.println(String(config_manager.getWiFiSSID().c_str()));
    display.setCursor(0, 46);
    display.println("Next: IP");
  } else {
    display.setCursor(0, 16);
    if (sta_connected && WiFi.status() == WL_CONNECTED) {
      display.println("IP Address:");
      display.setCursor(0, 30);
      display.println(WiFi.localIP().toString());
    } else {
      display.println("AP IP Address:");
      display.setCursor(0, 30);
      display.println(WiFi.softAPIP().toString());
    }
    display.setCursor(0, 46);
    display.println("Next: WiFi");
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
  display.println("Mark attendance");
  display.setCursor(0, 18);
  display.println("using fingerprint");
  display.display();
  attendancePromptVisible = true;
  idleStatusVisible = false;
}

void displayRegistrationResult(const String& name, uint16_t id, bool success) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  if (success) {
    display.println("Registration Successful");
  } else {
    display.println("Registration Failed");
  }
  display.setCursor(0, 16);
  display.println("Name: " + name.substring(0, 16));
  display.setCursor(0, 30);
  display.println("ID: " + String(id));
  display.display();
  attendancePromptVisible = false;
  idleStatusVisible = false;
  holdDisplayFor(success ? 2200 : 2800);
}

void displayAttendanceResult(bool success, const String& name, uint16_t id) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  if (success) {
    display.println("Attendance Marked");
    display.setCursor(0, 14);
    display.println("Successfuly");
    display.setCursor(0, 30);
    display.println(name.substring(0, 16));
  } else {
    display.println("Failed please");
    display.setCursor(0, 18);
    display.println("try again");
  }
  display.display();
  attendanceFeedbackUntilMs = millis() + (success ? 1800 : 3000);
  holdDisplayFor(success ? 1800 : 3000);
  attendancePromptVisible = false;
  idleStatusVisible = false;
}

void displayAttendanceRemoveFinger() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Attendance Marked");
  display.setCursor(0, 20);
  display.println("Remove Finger");
  display.display();
  attendanceFeedbackUntilMs = millis() + 2200;
  holdDisplayFor(2200);
  attendancePromptVisible = false;
  idleStatusVisible = false;
}

bool waitForAttendanceFingerRemoval(uint32_t timeoutMs) {
  Serial.println("[ATTENDANCE] waiting for finger removal");
  displayAttendanceRemoveFinger();
  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    if (!getImage()) {
      Serial.println("[ATTENDANCE] finger removed");
      return true;
    }
    delay(120);
  }
  Serial.println("[ATTENDANCE] finger removal timeout");
  return false;
}

String getStudentNameById(uint16_t id) {
  String key = String(id);
  if (studentRoster.containsKey(key)) {
    return studentRoster[key].as<String>();
  }
  return "Unknown";
}

void saveStudentRoster() {
  File file = SPIFFS.open("/students.json", "w");
  if (!file) {
    Serial.println("[ROSTER] failed to open /students.json for writing");
    return;
  }
  serializeJson(studentRoster, file);
  file.close();
}

void setStudentNameForId(uint16_t id, const String& name) {
  studentRoster[String(id)] = name;
  saveStudentRoster();
}

void removeStudentNameForId(uint16_t id) {
  studentRoster.remove(String(id));
  saveStudentRoster();
}

void setRegisterState(const String& state, const String& detail = "") {
  registerState = state;
  registerDetail = detail;
  Serial.print("[REGISTER_STATE] ");
  Serial.print(state);
  if (detail.length() > 0) {
    Serial.print(" | ");
    Serial.print(detail);
  }
  Serial.println();
}

// Function to calculate checksum
uint16_t calculateChecksum(uint8_t* data, int len) {
  uint16_t sum = 0;
  for (int i = 6; i < len - 2; i++) {
    sum += data[i];
  }
  return sum;
}

// Function to clear serial buffer
void clearSerialBuffer() {
  while (fingerSerial.available()) {
    fingerSerial.read();
  }
}

// Function to send command
void sendCommand(uint8_t* cmd, int len) {
  clearSerialBuffer();
  delay(10);
  for (int i = 0; i < len; i++) {
    fingerSerial.write(cmd[i]);
  }
  fingerSerial.flush();
  delay(50);
}

void printResponseBytes(const char* label, const uint8_t* buffer, int len) {
  Serial.print(label);
  Serial.print(": ");
  for (int i = 0; i < len; i++) {
    if (buffer[i] < 0x10) {
      Serial.print('0');
    }
    Serial.print(buffer[i], HEX);
    if (i < len - 1) {
      Serial.print(' ');
    }
  }
  Serial.println();
}

// Function to read response
bool readResponse(uint8_t* buffer, int len, int timeout = 1000) {
  int i = 0;
  unsigned long start = millis();
  while (millis() - start < timeout) {
    if (fingerSerial.available()) {
      buffer[i++] = fingerSerial.read();
      if (i >= len) {
        Serial.print("[FINGER] received ");
        Serial.print(len);
        Serial.println(" bytes");
        return true;
      }
    }
    delay(2);
  }
  Serial.print("[FINGER] timeout waiting for ");
  Serial.print(len);
  Serial.print(" bytes, got ");
  Serial.println(i);
  return false;
}

// Get image
bool getImage() {
  Serial.println("[FINGER] getImage");
  uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x01, 0x00, 0x05};
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[12];
  if (readResponse(response, 12, 1500)) {
    printResponseBytes("[FINGER] getImage response", response, 12);
    Serial.print("[FINGER] getImage status: ");
    Serial.println(response[9], HEX);
    return response[9] == 0x00;
  }
  return false;
}

bool waitForFingerImage(uint32_t timeoutMs) {
  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    if (getImage()) {
      return true;
    }
    delay(120);
  }
  return false;
}

// Generate character from image
bool genChar(uint8_t buffer);

bool captureFingerprint(uint8_t buffer, const String& label, uint32_t timeoutMs = 12000) {
  setRegisterState("waiting_" + label, registerTargetName + " | " + String(registerTargetId));
  if (label == "1st") {
    displayMessage("Place Finger", "1st scan");
  } else if (label == "2nd") {
    displayMessage("Place Again", "2nd scan");
  } else {
    displayMessage("Place Finger", label);
  }
  Serial.print("[FINGER] waiting for finger ");
  Serial.println(label);
  if (!waitForFingerImage(timeoutMs)) {
    displayMessage("Scan Failed", label);
    Serial.print("[FINGER] scan failed on step ");
    Serial.println(label);
    return false;
  }

  delay(500);
  for (int attempt = 0; attempt < 3; attempt++) {
    if (genChar(buffer)) {
      setRegisterState("captured_" + label, registerTargetName + " | " + String(registerTargetId));
      Serial.print("[FINGER] template captured in buffer ");
      Serial.println(buffer);
      return true;
    }
    Serial.print("[FINGER] genChar attempt ");
    Serial.print(attempt + 1);
    Serial.println(" failed, retrying...");
    delay(500);
  }

  displayMessage("Feature Fail", label);
  setRegisterState("failed", "feature extraction failed");
  Serial.print("[FINGER] feature extraction failed for step ");
  Serial.println(label);
  return false;
}

bool waitForFingerRemoval(uint32_t timeoutMs) {
  setRegisterState("remove_finger", registerTargetName + " | " + String(registerTargetId));
  displayMessage("Remove Finger", "now");
  Serial.println("[FINGER] waiting for finger removal");

  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    if (!getImage()) {
      Serial.println("[FINGER] finger removed");
      return true;
    }
    delay(120);
  }

  Serial.println("[FINGER] finger removal timeout");
  setRegisterState("failed", "finger removal timeout");
  displayMessage("Remove Timeout");
  return false;
}

// Generate character from image
bool genChar(uint8_t buffer) {
  Serial.print("[FINGER] genChar buffer ");
  Serial.println(buffer);
  uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x04, 0x02, buffer, 0x00, static_cast<uint8_t>(0x07 + buffer)};
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[12];
  // genChar can take up to 500-600ms to process, use 3000ms timeout
  if (readResponse(response, 12, 3000)) {
    printResponseBytes("[FINGER] genChar response", response, 12);
    Serial.print("[FINGER] genChar status: ");
    Serial.println(response[9], HEX);
    return response[9] == 0x00;
  }
  Serial.println("[FINGER] genChar timeout after 3000ms");
  return false;
}

// Create model
bool regModel() {
  setRegisterState("creating_model", registerTargetName + " | " + String(registerTargetId));
  Serial.println("[FINGER] regModel");
  uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x05, 0x00, 0x09};
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[12];
  if (readResponse(response, 12, 2000)) {
    printResponseBytes("[FINGER] regModel response", response, 12);
    Serial.print("[FINGER] regModel status: ");
    Serial.println(response[9], HEX);
    return response[9] == 0x00;
  }
  return false;
}

// Store model
bool storeModel(uint8_t buffer, uint16_t id) {
  setRegisterState("saving_model", registerTargetName + " | " + String(id));
  Serial.print("[FINGER] storeModel buffer ");
  Serial.print(buffer);
  Serial.print(" id ");
  Serial.println(id);
  uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x06, 0x06, buffer, (uint8_t)(id >> 8), (uint8_t)id, 0x00, static_cast<uint8_t>(0x0D + buffer + (uint8_t)(id >> 8) + (uint8_t)id)};
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[12];
  if (readResponse(response, 12, 2000)) {
    printResponseBytes("[FINGER] storeModel response", response, 12);
    Serial.print("[FINGER] storeModel status: ");
    Serial.println(response[9], HEX);
    return response[9] == 0x00;
  }
  return false;
}

// Search model
int searchModel(uint8_t buffer, uint16_t start, uint16_t end) {
  Serial.print("[FINGER] searchModel range ");
  Serial.print(start);
  Serial.print("- ");
  Serial.println(end);
  uint16_t checksum = 0x0D + buffer + (uint8_t)(start >> 8) + (uint8_t)start + (uint8_t)(end >> 8) + (uint8_t)end;
  uint8_t cmd[] = {
    0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF,
    0x01, 0x00, 0x08, 0x04, buffer,
    (uint8_t)(start >> 8), (uint8_t)start,
    (uint8_t)(end >> 8), (uint8_t)end,
    (uint8_t)(checksum >> 8), (uint8_t)checksum
  };
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[16];
  if (readResponse(response, 16, 2000)) {
    printResponseBytes("[FINGER] searchModel response", response, 16);
    if (response[9] == 0x00) {
      Serial.print("[FINGER] searchModel matched ID: ");
      Serial.println((response[10] << 8) | response[11]);
      return (response[10] << 8) | response[11];
    }
    Serial.print("[FINGER] searchModel status: ");
    Serial.println(response[9], HEX);
  }
  return -1;
}

// Delete model
bool deleteModel(uint16_t id) {
  Serial.print("[FINGER] deleteModel id ");
  Serial.println(id);
  uint16_t checksum = 0x15 + (uint8_t)(id >> 8) + (uint8_t)id;
  uint8_t cmd[] = {
    0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF,
    0x01, 0x00, 0x07, 0x0C,
    (uint8_t)(id >> 8), (uint8_t)id,
    0x00, 0x01,
    (uint8_t)(checksum >> 8), (uint8_t)checksum
  };
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[12];
  if (readResponse(response, 12, 2000)) {
    printResponseBytes("[FINGER] deleteModel response", response, 12);
    Serial.print("[FINGER] deleteModel status: ");
    Serial.println(response[9], HEX);
    return response[9] == 0x00;
  }
  return false;
}

// Empty database
bool emptyDatabase() {
  Serial.println("[FINGER] emptyDatabase");
  uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x0D, 0x00, 0x11};
  sendCommand(cmd, sizeof(cmd));
  uint8_t response[12];
  if (readResponse(response, 12)) {
    printResponseBytes("[FINGER] emptyDatabase response", response, 12);
    return response[9] == 0x00;
  }
  Serial.println("[FINGER] emptyDatabase timeout");
  return false;
}

// Enroll fingerprint
bool enrollFingerprint(uint16_t id) {
  // Clear existing slot first so re-registering the same ID does not fail early.
  Serial.println("[FINGER] begin enrollFingerprint");
  Serial.print("[FINGER] target ID: ");
  Serial.println(id);
  setRegisterState("starting", registerTargetName + " | " + String(id));
  if (!deleteModel(id)) {
    Serial.println("[FINGER] deleteModel did not confirm deletion, continuing anyway");
  }

  // Capture the same finger twice with explicit remove/place instructions.
  Serial.println("[FINGER] capture step 1 starting");
  displayMessage("Place Finger", "1st scan");
  if (!captureFingerprint(1, "1st")) return false;
  Serial.println("[FINGER] capture step 1 complete");
  delay(300);

  // Prevent duplicate enrollment under a different ID before asking for the second scan.
  displayMessage("Checking", "duplicates");
  int existingId = searchModel(1, 0, 255);
  if (existingId == -1) {
    delay(150);
    existingId = searchModel(1, 0, 255);
  }
  if (existingId >= 0 && existingId != id) {
    Serial.print("[FINGER] duplicate fingerprint detected, existing ID: ");
    Serial.println(existingId);
    setRegisterState("failed", "duplicate fingerprint: already ID " + String(existingId));
    displayMessage("Duplicate Finger", "ID " + String(existingId));
    return false;
  }

  if (!waitForFingerRemoval(10000)) return false;

  displayMessage("Place Again", "2nd scan");
  Serial.println("[FINGER] capture step 2 starting");
  if (!captureFingerprint(2, "2nd", 12000)) return false;
  Serial.println("[FINGER] capture step 2 complete");
  delay(400);
  // Create model
  displayMessage("Creating Model");
  Serial.println("[FINGER] creating model");
  for (int attempt = 0; attempt < 3; attempt++) {
    if (regModel()) {
      Serial.println("[FINGER] model created");
      break;
    }
    if (attempt == 2) {
      displayMessage("Model Failed");
      return false;
    }
    delay(300);
  }
  delay(500);
  // Store model
  displayMessage("Saving ID", String(id));
  Serial.println("[FINGER] saving model");
  for (int attempt = 0; attempt < 3; attempt++) {
    if (storeModel(1, id)) {
      Serial.println("[FINGER] storeModel success");
        setRegisterState("success", registerTargetName + " | " + String(id));
      return true;
    }
    if (attempt == 2) {
      displayMessage("Save Failed", String(id));
      setRegisterState("failed", "save failed");
      return false;
    }
    delay(300);
  }

  return false;
}

// Match fingerprint
int matchFingerprint() {
  Serial.println("[ATTENDANCE] waiting for finger");
  displayAttendancePrompt();
  if (!waitForFingerImage(8000)) {
    Serial.println("[ATTENDANCE] no finger detected in time");
    return -1;
  }

  delay(300);
  bool featureReady = false;
  for (int attempt = 0; attempt < 3; attempt++) {
    if (genChar(1)) {
      featureReady = true;
      break;
    }
    Serial.print("[ATTENDANCE] genChar retry ");
    Serial.println(attempt + 1);
    delay(250);
  }

  if (!featureReady) {
    Serial.println("[ATTENDANCE] feature extraction failed");
    return -1;
  }

  delay(200);
  int id = searchModel(1, 0, 255); // Search all enrolled IDs
  if (id == -1) {
    delay(150);
    id = searchModel(1, 0, 255);
  }
  Serial.print("[ATTENDANCE] match result: ");
  Serial.println(id);
  if (id == -1) {
    displayAttendanceResult(false, "", 0);
  }
  return id;
}

// Web handlers
void handleRegister(AsyncWebServerRequest *request) {
  if (request->hasParam("id")) {
    uint16_t id = request->getParam("id")->value().toInt();
    String studentName = "Student";
    if (request->hasParam("name")) {
      studentName = request->getParam("name")->value();
    }

    displayRegisterInfo(studentName, id);
    delay(1200);
  registerTargetId = id;
  registerTargetName = studentName;
    Serial.print("[REGISTER] student name: ");
    Serial.println(studentName);
    Serial.print("[REGISTER] student id: ");
    Serial.println(id);

    if (registerTaskHandle != nullptr) {
      request->send(409, "application/json", "{\"status\":\"error\",\"message\":\"Registration already running\"}");
      return;
    }

    auto registerTask = [](void *parameter) {
      setRegisterState("starting", registerTargetName + " | " + String(registerTargetId));
      bool success = enrollFingerprint(registerTargetId);
      if (success) {
        setStudentNameForId(registerTargetId, registerTargetName);
        displayRegistrationResult(registerTargetName, registerTargetId, true);
        Serial.println("[FINGER] registration successful");
        Serial.println("[REGISTER] completed successfully");
        setRegisterState("success", registerTargetName + " | " + String(registerTargetId));
      } else {
        displayRegistrationResult(registerTargetName, registerTargetId, false);
        Serial.println("[FINGER] registration failed");
        Serial.println("[REGISTER] completed with failure");
        setRegisterState("failed", registerTargetName + " | " + String(registerTargetId));
      }
      registerTaskHandle = nullptr;
      vTaskDelete(nullptr);
    };

    xTaskCreatePinnedToCore(registerTask, "registerTask", 8192, nullptr, 1, &registerTaskHandle, 0);
    request->send(202, "application/json", "{\"status\":\"started\"}");
    return;
  } else {
    request->send(400, "text/plain", "Missing id parameter");
  }
}

void handleRegisterStatus(AsyncWebServerRequest *request) {
  DynamicJsonDocument doc(256);
  doc["state"] = registerState;
  doc["detail"] = registerDetail;
  doc["id"] = registerTargetId;
  doc["name"] = registerTargetName;
  String json;
  serializeJson(doc, json);
  request->send(200, "application/json", json);
}

void handleAttendance(AsyncWebServerRequest *request) {
  int id = matchFingerprint();
  if (id != -1) {
    // Record attendance
    String time = String(millis());
    String studentName = getStudentNameById(id);
    attendance.add(JsonObject());
    JsonObject record = attendance[attendance.size() - 1];
    record["id"] = id;
    record["name"] = studentName;
    record["time"] = time;
    displayAttendanceResult(true, studentName, id);
    Serial.print("[ATTENDANCE] marked for ");
    Serial.print(studentName);
    Serial.print(" (ID: ");
    Serial.print(id);
    Serial.println(")");
    request->send(200, "text/plain", "Attendance marked for " + studentName + " (ID: " + String(id) + ")");
    waitForAttendanceFingerRemoval(1500);
  } else {
    Serial.println("[ATTENDANCE] no match found");
    request->send(400, "text/plain", "No match found");
  }
}

void handleGetAttendance(AsyncWebServerRequest *request) {
  String json;
  serializeJson(attendance, json);
  request->send(200, "application/json", json);
}

void handleClearAttendance(AsyncWebServerRequest *request) {
  attendance.clear();
  request->send(200, "text/plain", "Attendance cleared");
}

void handleDelete(AsyncWebServerRequest *request) {
  if (request->hasParam("id")) {
    uint16_t id = request->getParam("id")->value().toInt();
    if (deleteModel(id)) {
      removeStudentNameForId(id);
      request->send(200, "text/plain", "Deleted successfully");
    } else {
      request->send(400, "text/plain", "Delete failed");
    }
  } else {
    request->send(400, "text/plain", "Missing id parameter");
  }
}

void handleStatus(AsyncWebServerRequest *request) {
  DynamicJsonDocument doc(256);
  doc["sta_connected"] = sta_connected;
  doc["sta_ip"] = sta_connected ? WiFi.localIP().toString() : "";
  doc["ap_ip"] = WiFi.softAPIP().toString();
  doc["target_ssid"] = config_manager.getWiFiSSID();
  String json;
  serializeJson(doc, json);
  request->send(200, "application/json", json);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Initialize OLED Display
  Wire.begin(SDA_PIN, SCL_PIN);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 allocation failed");
  } else {
    displayMessage("System Ready");
  }
  delay(500);

  // Initialize SPIFFS
  if (!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
    return;
  }

  // Load config from SPIFFS
  config_manager.loadConfig();

  // Load attendance from file
  File file = SPIFFS.open("/attendance.json", "r");
  if (file) {
    deserializeJson(attendance, file);
    file.close();
  }

  File rosterFile = SPIFFS.open("/students.json", "r");
  if (rosterFile) {
    deserializeJson(studentRoster, rosterFile);
    rosterFile.close();
  }

  Serial.println("=== Fingerprint Attendance System READY ===");

  fingerSerial.begin(57600, SERIAL_8N1, RXD2, TXD2);

  // Wi-Fi mode: connect to hotspot as STA and keep fallback AP available.
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.println("Fallback AP started");
  Serial.print("Fallback AP IP: ");
  Serial.println(WiFi.softAPIP());

  // Parse IP configuration from config
  String staticIPStr = config_manager.getStaticIP();
  String gatewayStr = config_manager.getGateway();
  String subnetStr = config_manager.getSubnet();
  
  IPAddress staticIP;
  IPAddress gatewayIP;
  IPAddress subnetIP;
  
  staticIP.fromString(staticIPStr);
  gatewayIP.fromString(gatewayStr);
  subnetIP.fromString(subnetStr);

  WiFi.config(staticIP, gatewayIP, subnetIP);
  
  // Get WiFi credentials from config
  String ssid = config_manager.getWiFiSSID();
  String password = config_manager.getWiFiPassword();
  
  Serial.print("[CONFIG] WiFi SSID: ");
  Serial.println(ssid);
  Serial.print("[CONFIG] Static IP: ");
  Serial.println(staticIPStr);
  
  WiFi.begin(ssid.c_str(), password.c_str());

  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    sta_connected = true;
    Serial.println("WiFi STA connected");
    Serial.print("Router IP: ");
    Serial.println(WiFi.localIP());
  } else {
    sta_connected = false;
    Serial.println("WiFi STA connect failed, using AP mode");
  }

  displayIdleStatus();

  // Server routes
  server.on("/register", HTTP_GET, handleRegister);
  server.on("/register_status", HTTP_GET, handleRegisterStatus);
  server.on("/attendance", HTTP_GET, handleAttendance);
  server.on("/get_attendance", HTTP_GET, handleGetAttendance);
  server.on("/clear_attendance", HTTP_GET, handleClearAttendance);
  server.on("/delete", HTTP_GET, handleDelete);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/start_attendance", HTTP_GET, [](AsyncWebServerRequest *request) { 
    attendance_mode = true;
    attendanceFeedbackUntilMs = 0;
    displayAttendancePrompt();
    request->send(200, "text/plain", "Attendance started");
  });
  server.on("/stop_attendance", HTTP_GET, [](AsyncWebServerRequest *request) { 
    attendance_mode = false;
    attendanceFeedbackUntilMs = 0;
    displayMessage("Attendance Stopped");
    request->send(200, "text/plain", "Attendance stopped");
    delay(700);
    displayIdleStatus();
  });

  server.begin();
}

void loop() {
  if (millis() < displayHoldUntilMs) {
    delay(10);
    return;
  }

  if (isRegisterBusy()) {
    delay(10);
    return;
  }

  if (attendance_mode) {
    if (millis() > attendanceFeedbackUntilMs && !attendancePromptVisible) {
      displayAttendancePrompt();
    }
  } else {
    if (!idleStatusVisible || millis() - lastIdleRefreshMs > 4000) {
      displayIdleStatus();
    }
  }
  delay(10);
}