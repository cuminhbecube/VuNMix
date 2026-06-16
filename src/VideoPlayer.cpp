#include "VideoPlayer.h"
#include <TFT_eSPI.h>
#include <TJpg_Decoder.h>
#include "Config.h"

// Embedded AVI data - compiled directly into firmware flash
extern const uint8_t intro_avi_start[] asm("_binary_data_intro_avi_start");
extern const uint8_t intro_avi_end[]   asm("_binary_data_intro_avi_end");

namespace VideoPlayer {
    static TFT_eSPI s_tft;

    static bool tft_output(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
        if (y >= s_tft.height()) return 0;
        s_tft.pushImage(x, y, w, h, bitmap);
        return 1;
    }

    // Read a little-endian uint32 from a flash pointer
    static inline uint32_t readU32(const uint8_t* p) {
        return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
    }

    void Play(const char* filepath) {
        Serial.println("VideoPlayer: Waiting 2s for system to stabilize...");
        delay(2000);

        const uint8_t* data = intro_avi_start;
        const size_t dataLen = (size_t)(intro_avi_end - intro_avi_start);

        Serial.print("VideoPlayer: Embedded data size: ");
        Serial.println(dataLen);

        if (dataLen < 12) {
            Serial.println("VideoPlayer: Embedded data too small!");
            return;
        }

        // Quick RIFF check
        uint32_t magic = readU32(data);
        if (magic != 0x46464952) { // "RIFF"
            Serial.print("VideoPlayer: Not a valid RIFF/AVI. Magic: 0x");
            Serial.println(magic, HEX);
            return;
        }
        Serial.println("VideoPlayer: RIFF verified OK. Initializing display...");

        // Initialize TFT exclusively for video playback
        pinMode(PIN_TFT_BL, OUTPUT);
        s_tft.init();
        s_tft.setRotation(1); // Landscape 320x240
        s_tft.fillScreen(TFT_BLACK);
        s_tft.setSwapBytes(true);
        digitalWrite(PIN_TFT_BL, HIGH);

        // Setup TJpgDec
        TJpgDec.setJpgScale(1);
        TJpgDec.setCallback(tft_output);

        const uint32_t frameMs = 66; // ~15 FPS to match source video
        uint32_t framesPlayed = 0;
        size_t pos = 0;

        while (pos + 8 <= dataLen) {
            uint32_t chunkId   = readU32(data + pos); pos += 4;
            uint32_t chunkSize = readU32(data + pos); pos += 4;
            uint32_t paddedSize = (chunkSize + 1) & ~1;

            if (chunkId == 0x46464952) { // "RIFF"
                pos += 4; // skip "AVI " type
            } else if (chunkId == 0x5453494C) { // "LIST"
                uint32_t type = readU32(data + pos);
                pos += 4;
                if (type != 0x69766f6d) { // not "movi"
                    pos += paddedSize - 4; // skip non-movi LIST
                }
            } else if (chunkId == 0x63643030 || chunkId == 0x63643130) { // "00dc" or "01dc"
                if (chunkSize > 0 && chunkSize <= 50000 && pos + chunkSize <= dataLen) {
                    uint32_t frameStart = millis();

                    TJpgDec.drawJpg(0, 0, data + pos, chunkSize);
                    framesPlayed++;

                    uint32_t dt = millis() - frameStart;
                    if (dt < frameMs) delay(frameMs - dt);
                }
                pos += paddedSize;
            } else {
                pos += paddedSize; // skip unknown chunks
            }
        }

        Serial.print("VideoPlayer: Finished playing ");
        Serial.print(framesPlayed);
        Serial.println(" frames.");

        // Clear screen before handing back to LVGL
        s_tft.fillScreen(TFT_BLACK);
    }
}
