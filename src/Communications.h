#pragma once

#include "Config.h"

namespace Communications
{
    void Initialize(void);
    Command Read(void);
    void Write(Command command);
    void WriteImmediate(Command command);
    void SendPending(void);
}
