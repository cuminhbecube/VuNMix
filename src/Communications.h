#pragma once

#include "Config.h"

namespace Communications
{
    void Initialize(void);
    Command Read(void);
    void Write(Command command);
    void WriteImmediate(Command command);
    void SendPending(void);
    uint32_t ReceivedFrames(void);
    uint32_t TransmittedFrames(void);
    uint32_t CrcErrors(void);
    uint32_t ProtocolErrors(void);
    Command LastCommand(void);
    Command LastErrorCommand(void);
}
