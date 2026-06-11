#ifndef FINGERPRINT_H
#define FINGERPRINT_H

#include <Arduino.h>
#include <HardwareSerial.h>

// FPM383C packet header
#define FP_HEADER_1     0xEF
#define FP_HEADER_2     0x01
#define FP_ADDR_1       0xFF
#define FP_ADDR_2       0xFF
#define FP_ADDR_3       0xFF
#define FP_ADDR_4       0xFF

// Packet types
#define FP_CMD_PACKET   0x01
#define FP_DATA_PACKET  0x02
#define FP_ACK_PACKET   0x07
#define FP_END_PACKET   0x08

// Commands
#define FP_CMD_GENIMG       0x01
#define FP_CMD_IMG2TZ       0x02
#define FP_CMD_MATCH        0x03
#define FP_CMD_SEARCH       0x04
#define FP_CMD_REGMODEL     0x05
#define FP_CMD_STORE        0x06
#define FP_CMD_LOADCHAR     0x07
#define FP_CMD_UPCHAR       0x08  // Upload template from sensor to host
#define FP_CMD_DNCHAR       0x09  // Download template from host to sensor
#define FP_CMD_DELETE       0x0C
#define FP_CMD_EMPTY        0x0D
#define FP_CMD_TEMPLATENUM  0x1D

// Template size for FPM383C (typically 768 bytes per template)
#define FP_TEMPLATE_SIZE    768

class FingerprintSensor {
private:
    HardwareSerial& serial;
    
    void clearBuffer() {
        while (serial.available()) serial.read();
    }

    void sendPacket(uint8_t* data, int len) {
        clearBuffer();
        delay(10);
        serial.write(data, len);
        serial.flush();
        delay(50);
    }

    bool readPacket(uint8_t* buffer, int len, int timeout = 1000) {
        int i = 0;
        unsigned long start = millis();
        while (millis() - start < (unsigned long)timeout) {
            if (serial.available()) {
                buffer[i++] = serial.read();
                if (i >= len) return true;
            }
            delay(2);
        }
        return false;
    }

    // Read a variable-length response (header + data)
    int readFullResponse(uint8_t* buffer, int maxLen, int timeout = 2000) {
        int i = 0;
        unsigned long start = millis();
        // Read header (9 bytes minimum: 2 header + 4 addr + 1 type + 2 length)
        while (i < 9 && millis() - start < (unsigned long)timeout) {
            if (serial.available()) {
                buffer[i++] = serial.read();
            }
            delay(1);
        }
        if (i < 9) return i;
        
        // Extract packet length from bytes 7-8
        uint16_t pktLen = ((uint16_t)buffer[7] << 8) | buffer[8];
        int totalLen = 9 + pktLen;
        if (totalLen > maxLen) totalLen = maxLen;
        
        while (i < totalLen && millis() - start < (unsigned long)timeout) {
            if (serial.available()) {
                buffer[i++] = serial.read();
            }
            delay(1);
        }
        return i;
    }

public:
    FingerprintSensor(HardwareSerial& s) : serial(s) {}

    void begin(int baud, int rx, int tx) {
        serial.begin(baud, SERIAL_8N1, rx, tx);
    }

    // Capture image - returns true if finger detected
    bool getImage() {
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x01, 0x00, 0x05};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 1500)) {
            return resp[9] == 0x00;
        }
        return false;
    }

    // Generate character file from image
    bool img2Tz(uint8_t bufferId) {
        uint16_t chk = 0x01 + 0x00 + 0x04 + 0x02 + bufferId;
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x04, 0x02, bufferId,
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 3000)) {
            Serial.print("[FP] img2Tz resp[9]=0x");
            Serial.println(resp[9], HEX);
            return resp[9] == 0x00;
        }
        Serial.println("[FP] img2Tz timeout");
        return false;
    }

    // Create model from buffer 1 and 2
    bool regModel() {
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x05, 0x00, 0x09};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 2000)) {
            return resp[9] == 0x00;
        }
        return false;
    }

    // Store model to flash
    bool store(uint8_t bufferId, uint16_t id) {
        uint16_t chk = 0x01 + 0x00 + 0x06 + 0x06 + bufferId + (uint8_t)(id >> 8) + (uint8_t)(id & 0xFF);
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x06, 0x06, bufferId,
                         (uint8_t)(id >> 8), (uint8_t)(id & 0xFF),
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 2000)) {
            return resp[9] == 0x00;
        }
        return false;
    }

    // Load template from flash into buffer
    bool loadChar(uint8_t bufferId, uint16_t id) {
        Serial.print("[FP] loadChar buffer=");
        Serial.print(bufferId);
        Serial.print(" id=");
        Serial.println(id);
        uint16_t chk = 0x01 + 0x00 + 0x06 + 0x07 + bufferId + (uint8_t)(id >> 8) + (uint8_t)(id & 0xFF);
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x06, 0x07, bufferId,
                         (uint8_t)(id >> 8), (uint8_t)(id & 0xFF),
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 2000)) {
            Serial.print("[FP] loadChar resp=0x");
            Serial.println(resp[9], HEX);
            return resp[9] == 0x00;
        }
        Serial.println("[FP] loadChar timeout");
        return false;
    }

    // Upload template FROM sensor TO host (UpChar)
    // Returns number of bytes read into templateData, or -1 on failure
    int uploadTemplate(uint8_t bufferId, uint8_t* templateData, int maxLen) {
        // Send UpChar command
        uint16_t chk = 0x01 + 0x00 + 0x04 + 0x08 + bufferId;
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x04, 0x08, bufferId,
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        
        // Read ACK
        uint8_t ack[12];
        if (!readPacket(ack, 12, 2000)) return -1;
        if (ack[9] != 0x00) return -1;
        
        // Now read data packets until we get an end packet
        int totalRead = 0;
        unsigned long start = millis();
        while (millis() - start < 5000 && totalRead < maxLen) {
            // Read packet header (9 bytes)
            uint8_t hdr[9];
            if (!readPacket(hdr, 9, 2000)) break;
            
            uint8_t pktType = hdr[6];
            uint16_t pktLen = ((uint16_t)hdr[7] << 8) | hdr[8];
            
            // Read payload + checksum
            int dataLen = pktLen - 2;  // subtract 2 for checksum
            if (dataLen <= 0) break;
            if (totalRead + dataLen > maxLen) dataLen = maxLen - totalRead;
            
            // Read data bytes
            int bytesRead = 0;
            unsigned long pktStart = millis();
            while (bytesRead < dataLen && millis() - pktStart < 2000) {
                if (serial.available()) {
                    templateData[totalRead + bytesRead] = serial.read();
                    bytesRead++;
                }
                delay(1);
            }
            totalRead += bytesRead;
            
            // Read checksum (2 bytes)
            uint8_t chkBytes[2];
            readPacket(chkBytes, 2, 500);
            
            // End packet means we're done
            if (pktType == FP_END_PACKET) break;
        }
        
        Serial.print("[FP] uploadTemplate got ");
        Serial.print(totalRead);
        Serial.println(" bytes");
        return totalRead;
    }

    // Download template FROM host TO sensor (DnChar)
    bool downloadTemplate(uint8_t bufferId, const uint8_t* templateData, int dataLen) {
        Serial.print("[FP] downloadTemplate buffer=");
        Serial.print(bufferId);
        Serial.print(" len=");
        Serial.println(dataLen);
        
        // Send DnChar command
        uint16_t chk = 0x01 + 0x00 + 0x04 + 0x09 + bufferId;
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x04, 0x09, bufferId,
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        
        // Read ACK
        uint8_t ack[12];
        if (!readPacket(ack, 12, 2000)) {
            Serial.println("[FP] DnChar: no ACK");
            return false;
        }
        if (ack[9] != 0x00) {
            Serial.print("[FP] DnChar: ACK error 0x");
            Serial.println(ack[9], HEX);
            return false;
        }
        Serial.println("[FP] DnChar: ACK OK, sending data...");
        
        // Send template data in packets (128 bytes per data packet)
        int offset = 0;
        int packetSize = 128;
        
        while (offset < dataLen) {
            int remaining = dataLen - offset;
            int chunkLen = (remaining > packetSize) ? packetSize : remaining;
            bool isLast = (offset + chunkLen >= dataLen);
            uint8_t pktType = isLast ? FP_END_PACKET : FP_DATA_PACKET;
            
            // Packet length = data bytes + 2 (for checksum)
            uint16_t pktLen = chunkLen + 2;
            
            // Calculate checksum: sum of type + length_hi + length_lo + all data bytes
            uint16_t pktChk = pktType + (uint8_t)(pktLen >> 8) + (uint8_t)(pktLen & 0xFF);
            for (int i = 0; i < chunkLen; i++) {
                pktChk += templateData[offset + i];
            }
            
            // Send: header(6) + type(1) + length(2) + data(chunkLen) + checksum(2)
            uint8_t hdr[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, pktType,
                            (uint8_t)(pktLen >> 8), (uint8_t)(pktLen & 0xFF)};
            serial.write(hdr, 9);
            serial.write(&templateData[offset], chunkLen);
            serial.write((uint8_t)(pktChk >> 8));
            serial.write((uint8_t)(pktChk & 0xFF));
            serial.flush();
            
            offset += chunkLen;
            delay(10);
        }
        
        Serial.println("[FP] DnChar: data sent, waiting for confirmation...");
        delay(100);
        
        // Some sensors don't send a final ACK for DnChar, just return true
        return true;
    }

    // Search for a match
    int search(uint8_t bufferId, uint16_t startId, uint16_t count) {
        uint16_t chk = 0x01 + 0x00 + 0x08 + 0x04 + bufferId + 
                       (uint8_t)(startId >> 8) + (uint8_t)(startId & 0xFF) +
                       (uint8_t)(count >> 8) + (uint8_t)(count & 0xFF);
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x08, 0x04, bufferId,
                         (uint8_t)(startId >> 8), (uint8_t)(startId & 0xFF),
                         (uint8_t)(count >> 8), (uint8_t)(count & 0xFF),
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[16];
        if (readPacket(resp, 16, 2000)) {
            if (resp[9] == 0x00) {
                return (resp[10] << 8) | resp[11];
            }
        }
        return -1;
    }

    // Delete a template
    bool deleteTemplate(uint16_t id, uint16_t count = 1) {
        uint16_t chk = 0x01 + 0x00 + 0x07 + 0x0C + 
                       (uint8_t)(id >> 8) + (uint8_t)(id & 0xFF) +
                       (uint8_t)(count >> 8) + (uint8_t)(count & 0xFF);
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x07, 0x0C,
                         (uint8_t)(id >> 8), (uint8_t)(id & 0xFF),
                         (uint8_t)(count >> 8), (uint8_t)(count & 0xFF),
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 2000)) {
            return resp[9] == 0x00;
        }
        return false;
    }

    // Empty all templates
    bool emptyDatabase() {
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x0D, 0x00, 0x11};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[12];
        if (readPacket(resp, 12, 2000)) {
            return resp[9] == 0x00;
        }
        return false;
    }

    // Get template count
    int getTemplateCount() {
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x03, 0x1D, 0x00, 0x21};
        sendPacket(cmd, sizeof(cmd));
        uint8_t resp[14];
        if (readPacket(resp, 14, 2000)) {
            if (resp[9] == 0x00) {
                return (resp[10] << 8) | resp[11];
            }
        }
        return -1;
    }

    // Wait for finger placement
    bool waitForFinger(uint32_t timeoutMs) {
        unsigned long start = millis();
        while (millis() - start < timeoutMs) {
            if (getImage()) return true;
            delay(120);
        }
        return false;
    }

    // Wait for finger removal
    bool waitForRemoval(uint32_t timeoutMs) {
        unsigned long start = millis();
        while (millis() - start < timeoutMs) {
            if (!getImage()) return true;
            delay(120);
        }
        return false;
    }
};

#endif
