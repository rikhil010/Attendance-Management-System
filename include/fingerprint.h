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

    // Read a single byte with timeout, returns -1 if timeout
    int waitReadByte(int timeout) {
        unsigned long start = millis();
        while (millis() - start < (unsigned long)timeout) {
            if (serial.available()) return serial.read();
            delay(1);
        }
        return -1;
    }

    // Read exactly n bytes into buf, returns true if all read
    bool readExact(uint8_t* buf, int n, int timeout) {
        int i = 0;
        unsigned long start = millis();
        while (i < n && millis() - start < (unsigned long)timeout) {
            if (serial.available()) {
                buf[i++] = serial.read();
            } else {
                delay(1);
            }
        }
        return i == n;
    }

    // Scan the stream until we find packet header 0xEF 0x01
    bool syncToHeader(int timeout) {
        unsigned long start = millis();
        int state = 0;
        while (millis() - start < (unsigned long)timeout) {
            if (serial.available()) {
                uint8_t b = serial.read();
                if (state == 0 && b == 0xEF) state = 1;
                else if (state == 1 && b == 0x01) return true;
                else state = (b == 0xEF) ? 1 : 0;
            } else {
                delay(1);
            }
        }
        return false;
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

    // EXPORT: Upload character file FROM sensor (UpChar, cmd 0x08)
    // Reads packets dynamically, STOPS at End-of-Data packet (pid 0x08) with
    // checksum verification. Returns exact template length, or -1 on failure.
    int uploadTemplate(uint8_t bufferId, uint8_t* templateData, int maxLen) {
        clearBuffer();
        // Send UpChar command
        uint16_t cchk = 0x01 + 0x00 + 0x04 + 0x08 + bufferId;
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x04, 0x08, bufferId,
                         (uint8_t)(cchk >> 8), (uint8_t)(cchk & 0xFF)};
        serial.write(cmd, sizeof(cmd));
        serial.flush();

        // Read ACK packet (sync to header, then 12 bytes total)
        if (!syncToHeader(2000)) { Serial.println("[FP] UpChar: no ACK header"); return -1; }
        uint8_t ackRest[10];  // addr(4)+pid(1)+len(2)+code(1)+chk(2) = 10 after EF01
        if (!readExact(ackRest, 10, 2000)) { Serial.println("[FP] UpChar: ACK short"); return -1; }
        if (ackRest[4] != 0x07 || ackRest[7] != 0x00) {
            Serial.print("[FP] UpChar: ACK code 0x"); Serial.println(ackRest[7], HEX);
            return -1;
        }

        // Read data packets sequentially until end packet (pid 0x08)
        int totalRead = 0;
        int packetCount = 0;
        bool gotEnd = false;
        while (packetCount < 64) {
            // Sync to next packet header (data content rarely contains EF01;
            // sequential length-advance keeps us aligned)
            if (!syncToHeader(2000)) {
                Serial.println("[FP] UpChar: packet header timeout");
                break;
            }
            // Read addr(4) + pid(1) + len(2) = 7 bytes
            uint8_t hdr[7];
            if (!readExact(hdr, 7, 2000)) break;
            uint8_t pid = hdr[4];
            uint16_t pktLen = ((uint16_t)hdr[5] << 8) | hdr[6];
            int contentLen = pktLen - 2;  // exclude 2-byte checksum
            if (contentLen <= 0 || contentLen > 256) {
                Serial.print("[FP] UpChar: bad content len "); Serial.println(contentLen);
                break;
            }
            // Read content
            uint8_t content[256];
            if (!readExact(content, contentLen, 3000)) { Serial.println("[FP] UpChar: content short"); break; }
            // Read checksum (2 bytes) and verify
            uint8_t cs[2];
            if (!readExact(cs, 2, 1000)) break;
            uint16_t calc = pid + hdr[5] + hdr[6];
            for (int i = 0; i < contentLen; i++) calc += content[i];
            uint16_t recv = ((uint16_t)cs[0] << 8) | cs[1];
            if (calc != recv) {
                Serial.print("[FP] UpChar: checksum mismatch pkt "); Serial.println(packetCount);
                break;
            }
            // Append content
            for (int i = 0; i < contentLen && totalRead < maxLen; i++) {
                templateData[totalRead++] = content[i];
            }
            packetCount++;
            if (pid == 0x08) { gotEnd = true; break; }  // End-of-Data
        }

        Serial.print("[FP] UpChar: ");
        Serial.print(totalRead);
        Serial.print(" bytes, ");
        Serial.print(packetCount);
        Serial.print(" packets, end=");
        Serial.println(gotEnd ? "yes" : "no");
        return gotEnd ? totalRead : -1;  // only valid if we saw the end packet
    }

    // Download template FROM host TO sensor (DnChar)
    // Sends complete character file in data packets matching sensor's format
    bool downloadTemplate(uint8_t bufferId, const uint8_t* templateData, int dataLen) {
        Serial.print("[FP] DnChar buffer=");
        Serial.print(bufferId);
        Serial.print(" len=");
        Serial.println(dataLen);

        clearBuffer();
        // Send DnChar command: cmd=0x09, bufferId
        uint16_t chk = 0x01 + 0x00 + 0x04 + 0x09 + bufferId;
        uint8_t cmd[] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x00, 0x04, 0x09, bufferId,
                         (uint8_t)(chk >> 8), (uint8_t)(chk & 0xFF)};
        serial.write(cmd, sizeof(cmd));
        serial.flush();
        delay(20);

        // Read ACK packet
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

        // Send data in packets. Content size 128 bytes per packet.
        const int CONTENT = 128;
        int offset = 0;
        while (offset < dataLen) {
            int chunk = dataLen - offset;
            if (chunk > CONTENT) chunk = CONTENT;
            bool isLast = (offset + chunk >= dataLen);
            uint8_t pid = isLast ? 0x08 : 0x02;

            uint16_t pktLen = chunk + 2;  // content + 2 checksum bytes
            uint16_t pktChk = pid + (uint8_t)(pktLen >> 8) + (uint8_t)(pktLen & 0xFF);

            // Header: EF 01 FF FF FF FF [pid] [len_hi] [len_lo]
            uint8_t hdr[9] = {0xEF, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, pid,
                              (uint8_t)(pktLen >> 8), (uint8_t)(pktLen & 0xFF)};
            serial.write(hdr, 9);

            // Data + accumulate checksum
            for (int i = 0; i < chunk; i++) {
                uint8_t b = templateData[offset + i];
                serial.write(b);
                pktChk += b;
            }
            // Checksum
            serial.write((uint8_t)(pktChk >> 8));
            serial.write((uint8_t)(pktChk & 0xFF));
            serial.flush();

            offset += chunk;
            delay(15);
        }

        delay(150);  // Let sensor process
        Serial.println("[FP] DnChar: data sent");
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
