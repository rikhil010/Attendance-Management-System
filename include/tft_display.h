#ifndef TFT_DISPLAY_H
#define TFT_DISPLAY_H

#include <Arduino.h>
#include <TFT_eSPI.h>

/**
 * Drop-in replacement for the Adafruit_SSD1306 API, backed by a 320x240
 * ILI9341 TFT via TFT_eSPI. Lets all existing display.*() calls keep working.
 *
 * Direct-draw implementation (no off-screen sprite). An 8-bit full-screen
 * sprite proved unreliable on this breadboard wiring (garbled / repeated /
 * partially-rendered frames), so we draw straight to the panel. Text is drawn
 * opaque (foreground over a solid background colour) so each redraw cleanly
 * overwrites the previous one without a full-screen wipe — no visible flicker
 * for the simple text screens this app uses.
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

    TftDisplay() {}

    bool begin(uint8_t = 0, uint8_t = 0) {
        tft.init();
        tft.setRotation(1);                 // landscape: 320 x 240
        tft.fillScreen(TFT_BLACK);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);   // opaque text (fg over bg)
        tft.setTextSize(2);
        _fg = TFT_WHITE;
        return true;
    }

    // Clear the panel. Done once per full redraw; text then overwrites opaquely.
    void clearDisplay() {
        tft.fillScreen(TFT_BLACK);
        setCursorRaw(0, 0);
    }

    // No back buffer to push — drawing already happened on the panel.
    void display() {}

    void setTextSize(uint8_t s) {                 // OLED size 1->2, 2->3
        tft.setTextSize(s + 1);
    }

    void setTextColor(uint16_t c) {
        _fg = (c == 0) ? TFT_BLACK : TFT_WHITE;
        tft.setTextColor(_fg, TFT_BLACK);         // always opaque over black
    }
    void setTextColor(uint16_t fg, uint16_t bg) {
        uint16_t f = (fg == 0) ? TFT_BLACK : TFT_WHITE;
        uint16_t b = (bg == 0) ? TFT_BLACK : TFT_WHITE;
        _fg = f;
        tft.setTextColor(f, b);
    }

    void setCursor(int16_t x, int16_t y) {
        setCursorRaw((int16_t)(x * SCALE_X), (int16_t)(y * SCALE_Y));
    }

    void print(const String& s)   { tft.print(s); }
    void print(const char* s)     { tft.print(s); }
    void print(int v)             { tft.print(v); }
    void println(const String& s) { tft.println(s); }
    void println(const char* s)   { tft.println(s); }
    void println(int v)           { tft.println(v); }
    void println()                { tft.println(); }

private:
    void setCursorRaw(int16_t x, int16_t y) {
        tft.setCursor(x, y);
    }

    uint16_t _fg = TFT_WHITE;

    static constexpr int16_t SCREEN_W = 320;
    static constexpr int16_t SCREEN_H = 240;
    static constexpr float   SCALE_X  = 2.2f;   // 128 -> ~282
    static constexpr float   SCALE_Y  = 3.0f;   // 64  -> 192
};

#endif // TFT_DISPLAY_H
