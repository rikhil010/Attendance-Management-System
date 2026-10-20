#ifndef TFT_DISPLAY_H
#define TFT_DISPLAY_H

#include <Arduino.h>
#include <TFT_eSPI.h>

/**
 * Drop-in replacement for the Adafruit_SSD1306 API, backed by a 320x240
 * ILI9341 TFT via TFT_eSPI. Lets all existing display.*() calls keep working.
 *
 * Flicker-free: all drawing goes to an off-screen sprite (back buffer) and is
 * pushed to the panel in one operation on display(), so no full-screen wipe is
 * ever visible. Falls back to direct drawing if the sprite can't allocate.
 *
 * The original UI targeted a 128x64 OLED; coordinates/text are scaled up for
 * the 320x240 landscape panel.
 */

#ifndef SSD1306_WHITE
#define SSD1306_WHITE 1
#endif
#ifndef SSD1306_BLACK
#define SSD1306_BLACK 0
#endif
#ifndef SSD1306_SWITCHCAPVCC
#define SSD1306_SWITCHCAPVCC 0x02
#endif

class TftDisplay {
public:
    TFT_eSPI tft;

    TftDisplay() : _spr(&tft) {}

    bool begin(uint8_t = 0, uint8_t = 0) {
        tft.init();
        tft.setRotation(1);                 // landscape: 320 x 240
        tft.fillScreen(TFT_BLACK);

        _spr.setColorDepth(8);              // 8-bit back buffer (~75KB)
        void* buf = _spr.createSprite(SCREEN_W, SCREEN_H);
        _useSprite = (buf != nullptr);
        if (!_useSprite) Serial.println("[TFT] Sprite alloc failed - direct draw");

        _spr.setTextColor(TFT_WHITE);
        tft.setTextColor(TFT_WHITE);
        return true;
    }

    void clearDisplay() {
        if (_useSprite) _spr.fillSprite(TFT_BLACK);
        else            tft.fillScreen(TFT_BLACK);
        setCursorRaw(0, 0);
    }

    void display() { if (_useSprite) _spr.pushSprite(0, 0); }

    void setTextSize(uint8_t s) {                 // OLED size 1->2, 2->3
        uint8_t t = s + 1;
        if (_useSprite) _spr.setTextSize(t); else tft.setTextSize(t);
    }

    void setTextColor(uint16_t c) {
        uint16_t col = (c == 0) ? TFT_BLACK : TFT_WHITE;
        if (_useSprite) _spr.setTextColor(col); else tft.setTextColor(col);
    }
    void setTextColor(uint16_t fg, uint16_t bg) {
        uint16_t f = (fg == 0) ? TFT_BLACK : TFT_WHITE;
        uint16_t b = (bg == 0) ? TFT_BLACK : TFT_WHITE;
        if (_useSprite) _spr.setTextColor(f, b); else tft.setTextColor(f, b);
    }

    void setCursor(int16_t x, int16_t y) {
        setCursorRaw((int16_t)(x * SCALE_X), (int16_t)(y * SCALE_Y));
    }

    void print(const String& s)   { if (_useSprite) _spr.print(s);   else tft.print(s); }
    void print(const char* s)     { if (_useSprite) _spr.print(s);   else tft.print(s); }
    void print(int v)             { if (_useSprite) _spr.print(v);   else tft.print(v); }
    void println(const String& s) { if (_useSprite) _spr.println(s); else tft.println(s); }
    void println(const char* s)   { if (_useSprite) _spr.println(s); else tft.println(s); }
    void println(int v)           { if (_useSprite) _spr.println(v); else tft.println(v); }
    void println()                { if (_useSprite) _spr.println();  else tft.println(); }

private:
    void setCursorRaw(int16_t x, int16_t y) {
        if (_useSprite) _spr.setCursor(x, y); else tft.setCursor(x, y);
    }

    TFT_eSprite _spr;
    bool _useSprite = false;

    static constexpr int16_t SCREEN_W = 320;
    static constexpr int16_t SCREEN_H = 240;
    static constexpr float   SCALE_X  = 2.2f;   // 128 -> ~282
    static constexpr float   SCALE_Y  = 3.0f;   // 64  -> 192
};

#endif // TFT_DISPLAY_H
