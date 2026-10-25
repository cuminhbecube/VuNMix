#pragma once

#include <stdint.h>

// Optional protocol-v1 extension. The legacy 19-byte SETTINGS record and
// the four clock-style bits are deliberately not involved in theme selection.
namespace DeviceThemeProtocol {
    static constexpr uint8_t COUNT = 8;
    static constexpr uint8_t SUPPORTED_MASK = 0xFF;
    static constexpr uint8_t SCHEMA_VERSION = 1;

    enum class Operation : uint8_t { QUERY = 0, SET = 1 };
    enum class Status : uint8_t {
        APPLIED = 0,
        SAVED_DEFERRED = 1,
        UNSUPPORTED = 2,
        INVALID = 3,
        BUSY = 4,
        FAILED = 5
    };

    struct __attribute__((__packed__)) Request {
        uint8_t operation;
        uint8_t themeId;
        uint16_t requestId;
    };

    struct __attribute__((__packed__)) Response {
        uint16_t requestId;
        uint8_t status;
        uint8_t configuredThemeId;
        uint8_t supportedMask;
        uint8_t schemaVersion;
    };

    static_assert(sizeof(Request) == 4, "UI_THEME request must be 4 bytes");
    static_assert(sizeof(Response) == 6, "UI_THEME response must be 6 bytes");
}
