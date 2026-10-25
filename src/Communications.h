#pragma once

#include "Config.h"
#include "DeviceThemeProtocol.h"

namespace Communications
{
    void Initialize(void);
    Command Read(void);
    void Write(Command command);
    void WriteImmediate(Command command);
    void SendPending(void);
    void SendMediaControl(uint8_t action);
    bool TakeDeviceThemeRequest(DeviceThemeProtocol::Request& request);
    void SendDeviceThemeStatus(uint16_t requestId, DeviceThemeProtocol::Status status,
                               uint8_t configuredThemeId);
    uint32_t ReceivedFrames(void);
    uint32_t TransmittedFrames(void);
    uint32_t CrcErrors(void);
    uint32_t ProtocolErrors(void);
    Command LastCommand(void);
    Command LastErrorCommand(void);
}
