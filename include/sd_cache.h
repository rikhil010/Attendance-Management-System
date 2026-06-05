#ifndef SD_CACHE_H
#define SD_CACHE_H

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include "pins.h"

class SDCache {
private:
    bool initialized;

public:
    SDCache() : initialized(false) {}

    bool begin() {
        SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
        if (!SD.begin(PIN_SD_CS)) {
            Serial.println("[SD] Card mount failed");
            initialized = false;
            return false;
        }
        Serial.println("[SD] Card mounted successfully");
        Serial.print("[SD] Card size: ");
        Serial.print(SD.cardSize() / (1024 * 1024));
        Serial.println(" MB");
        initialized = true;
        
        // Create base directories
        if (!SD.exists("/templates")) SD.mkdir("/templates");
        if (!SD.exists("/attendance")) SD.mkdir("/attendance");
        return true;
    }

    bool isReady() { return initialized; }

    // Save a fingerprint template to SD card
    // Path: /templates/{classId}/{studentId}.bin
    bool saveTemplate(int classId, int studentId, const uint8_t* data, int len) {
        if (!initialized) return false;
        
        String dirPath = "/templates/" + String(classId);
        if (!SD.exists(dirPath)) {
            SD.mkdir(dirPath);
        }
        
        String filePath = dirPath + "/" + String(studentId) + ".bin";
        File file = SD.open(filePath, FILE_WRITE);
        if (!file) {
            Serial.print("[SD] Failed to open for write: ");
            Serial.println(filePath);
            return false;
        }
        
        size_t written = file.write(data, len);
        file.close();
        
        Serial.print("[SD] Saved template: ");
        Serial.print(filePath);
        Serial.print(" (");
        Serial.print(written);
        Serial.println(" bytes)");
        return written == (size_t)len;
    }

    // Load a fingerprint template from SD card
    // Returns number of bytes read, or -1 on failure
    int loadTemplate(int classId, int studentId, uint8_t* data, int maxLen) {
        if (!initialized) return -1;
        
        String filePath = "/templates/" + String(classId) + "/" + String(studentId) + ".bin";
        File file = SD.open(filePath, FILE_READ);
        if (!file) {
            Serial.print("[SD] Template not found: ");
            Serial.println(filePath);
            return -1;
        }
        
        int bytesRead = file.read(data, maxLen);
        file.close();
        return bytesRead;
    }

    // Check if a template exists
    bool templateExists(int classId, int studentId) {
        if (!initialized) return false;
        String filePath = "/templates/" + String(classId) + "/" + String(studentId) + ".bin";
        return SD.exists(filePath);
    }

    // Delete a template
    bool deleteTemplate(int classId, int studentId) {
        if (!initialized) return false;
        String filePath = "/templates/" + String(classId) + "/" + String(studentId) + ".bin";
        return SD.remove(filePath);
    }

    // List all student IDs with templates for a class
    int listClassTemplates(int classId, int* studentIds, int maxCount) {
        if (!initialized) return 0;
        
        String dirPath = "/templates/" + String(classId);
        File dir = SD.open(dirPath);
        if (!dir || !dir.isDirectory()) return 0;
        
        int count = 0;
        File entry;
        while ((entry = dir.openNextFile()) && count < maxCount) {
            String name = String(entry.name());
            // Extract student ID from filename (e.g., "47.bin" → 47)
            int dotIdx = name.lastIndexOf('.');
            if (dotIdx > 0) {
                String idStr = name.substring(0, dotIdx);
                studentIds[count++] = idStr.toInt();
            }
            entry.close();
        }
        dir.close();
        return count;
    }

    // Save attendance log entry
    bool logAttendance(int classId, int sessionId, int studentId, const String& name, const String& timestamp) {
        if (!initialized) return false;
        
        String filePath = "/attendance/session_" + String(sessionId) + ".csv";
        File file = SD.open(filePath, FILE_APPEND);
        if (!file) {
            // Create with header
            file = SD.open(filePath, FILE_WRITE);
            if (!file) return false;
            file.println("student_id,name,timestamp,class_id");
        }
        
        file.print(studentId);
        file.print(",");
        file.print(name);
        file.print(",");
        file.print(timestamp);
        file.print(",");
        file.println(classId);
        file.close();
        return true;
    }

    // Get total and used space
    uint64_t getTotalBytes() { return initialized ? SD.totalBytes() : 0; }
    uint64_t getUsedBytes() { return initialized ? SD.usedBytes() : 0; }
};

#endif
