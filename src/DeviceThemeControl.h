#pragma once

#include "DeviceThemeProtocol.h"

namespace DeviceThemeControl {
    struct Preparation {
        DeviceThemeProtocol::Status status;
        bool render;
    };

    // Selection updates no LVGL objects. Only a successfully persisted change
    // may request a non-clock redraw; clock/sleep transitions remain owned by
    // the existing main-loop state machine. Callers finalize APPLIED after draw.
    template <typename Select, typename Persist>
    Preparation Prepare(const DeviceThemeProtocol::Request& request,
                        uint8_t currentTheme, bool deferred,
                        Select select, Persist persist) {
        using DeviceThemeProtocol::Operation;
        using DeviceThemeProtocol::Status;
        const Status success = deferred ? Status::SAVED_DEFERRED : Status::APPLIED;
        if (request.operation == static_cast<uint8_t>(Operation::QUERY))
            return {success, false};
        if (request.operation != static_cast<uint8_t>(Operation::SET)
                || request.themeId >= DeviceThemeProtocol::COUNT)
            return {Status::INVALID, false};
        if (request.themeId == currentTheme)
            return {success, false};
        if (!select(request.themeId))
            return {Status::FAILED, false};
        if (!persist(request.themeId)) {
            select(currentTheme);
            return {Status::FAILED, false};
        }
        return {success, !deferred};
    }
}
