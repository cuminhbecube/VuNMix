#include "Communications.h"
#include "Display.h"

// Defined in main.cpp
extern DeviceSettings g_Settings;
extern SessionInfo g_SessionInfo;
extern SessionData g_Sessions[4];
extern ModeStates g_ModeStates;
extern MeterData g_MeterData;
extern uint32_t g_HeartbeatTimeout;
extern uint32_t g_Now;
extern uint32_t g_LastSteps;
extern TimeData g_TimeData;
extern uint32_t g_TimeSyncMillis;
extern bool g_TimeValid;

namespace Communications
{
    static constexpr uint8_t FRAME_MAGIC_0 = 0xA5;
    static constexpr uint8_t FRAME_MAGIC_1 = 0x5A;
    static constexpr uint8_t MAX_PAYLOAD = 64;
    // A complete state burst is roughly 170 bytes (info, mode state and
    // current/previous/next sessions). Keep enough headroom so USB CDC can
    // deliver several frames in one packet without discarding the first one.
    static constexpr uint16_t RX_BUFFER_SIZE = 512;

    static uint8_t s_rxBuffer[RX_BUFFER_SIZE];
    static uint16_t s_rxLength = 0;

    static constexpr uint8_t TX_QUEUE_SIZE = 16;
    static Command s_txQueue[TX_QUEUE_SIZE];
    static uint8_t s_txHead = 0;
    static uint8_t s_txTail = 0;
    static uint8_t s_txCount = 0;
    static uint32_t s_receivedFrames = 0;
    static uint32_t s_transmittedFrames = 0;
    static uint32_t s_crcErrors = 0;
    static uint32_t s_protocolErrors = 0;
    static Command s_lastCommand = Command::NONE;
    static Command s_lastErrorCommand = Command::NONE;

    static uint16_t Crc16(const uint8_t *data, size_t length)
    {
        uint16_t crc = 0xFFFF;
        for (size_t i = 0; i < length; ++i)
        {
            crc ^= (uint16_t)data[i] << 8;
            for (uint8_t bit = 0; bit < 8; ++bit)
                crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
        return crc;
    }

    static void DiscardRx(uint16_t count)
    {
        if (count >= s_rxLength)
        {
            s_rxLength = 0;
            return;
        }
        memmove(s_rxBuffer, s_rxBuffer + count, s_rxLength - count);
        s_rxLength -= count;
    }

    static void SendFrame(Command command, const void *payload = nullptr, uint8_t payloadLength = 0)
    {
        if (payloadLength > MAX_PAYLOAD) return;

        uint8_t frame[2 + 2 + MAX_PAYLOAD + 2];
        frame[0] = FRAME_MAGIC_0;
        frame[1] = FRAME_MAGIC_1;
        frame[2] = (uint8_t)command;
        frame[3] = payloadLength;
        if (payloadLength > 0 && payload != nullptr)
            memcpy(frame + 4, payload, payloadLength);

        uint16_t crc = Crc16(frame + 2, (size_t)payloadLength + 2);
        frame[4 + payloadLength] = (uint8_t)(crc & 0xFF);
        frame[5 + payloadLength] = (uint8_t)(crc >> 8);
        // USB CDC writes are buffered. Do not wait for the host here: a slow
        // or disconnected host must not stall the input/LVGL main loop.
        Serial.write(frame, (size_t)payloadLength + 6);
        ++s_transmittedFrames;
    }

    static void TxEnqueue(Command command)
    {
        if (s_txCount >= TX_QUEUE_SIZE)
        {
            // Commands carry snapshots of the latest global state. Prefer the
            // newest snapshot over an old queue entry if the consumer stalls.
            s_txTail = (s_txTail + 1) % TX_QUEUE_SIZE;
            --s_txCount;
        }
        s_txQueue[s_txHead] = command;
        s_txHead = (s_txHead + 1) % TX_QUEUE_SIZE;
        ++s_txCount;
    }

    static Command TxDequeue()
    {
        if (s_txCount == 0) return Command::NONE;
        Command command = s_txQueue[s_txTail];
        s_txTail = (s_txTail + 1) % TX_QUEUE_SIZE;
        --s_txCount;
        return command;
    }

    static Command ProcessFrame(Command command, const uint8_t *payload, uint8_t payloadLength)
    {
        if (command == Command::TEST)
        {
            if (payloadLength != 0) return Command::ERROR;
            WriteImmediate(Command::TEST);
        }
        else if (command == Command::OK || command == Command::SLEEP)
        {
            if (payloadLength != 0) return Command::ERROR;
        }
        else if (command == Command::SETTINGS)
        {
            if (payloadLength != sizeof(DeviceSettings)) return Command::ERROR;
            DeviceSettings settings;
            memcpy(&settings, payload, sizeof(DeviceSettings));
            settings.accelerationPercentage = min((uint8_t)100, settings.accelerationPercentage);
            if (settings.standbyLedMode > 15) settings.standbyLedMode = 0;
            g_Settings = settings;
        }
        else if (command == Command::SESSION_INFO)
        {
            if (payloadLength != sizeof(SessionInfo)) return Command::ERROR;
            SessionInfo info;
            memcpy(&info, payload, sizeof(SessionInfo));
            if (info.mode >= DisplayMode::MODE_MAX) return Command::ERROR;
            uint8_t modeIndex = info.mode == DisplayMode::MODE_INPUT ? 1
                              : (info.mode == DisplayMode::MODE_APPLICATION || info.mode == DisplayMode::MODE_GAME) ? 2
                              : 0;
            if (info.sessions[modeIndex] > 0 && info.current >= info.sessions[modeIndex])
                info.current = info.sessions[modeIndex] - 1;
            g_SessionInfo = info;
        }
        else if (command >= Command::CURRENT_SESSION && command <= Command::NEXT_SESSION)
        {
            if (payloadLength != sizeof(SessionData)) return Command::ERROR;
            memcpy(&g_Sessions[(int8_t)command - (int8_t)Command::CURRENT_SESSION],
                   payload, sizeof(SessionData));
            // Always guarantee termination before constructing Arduino String/LVGL text.
            SessionData &session = g_Sessions[(int8_t)command - (int8_t)Command::CURRENT_SESSION];
            session.name[29] = '\0';
            session.data.volume = min((uint8_t)100, session.data.volume);
        }
        else if (command >= Command::VOLUME_CURR_CHANGE && command <= Command::VOLUME_NEXT_CHANGE)
        {
            if (payloadLength != sizeof(VolumeData)) return Command::ERROR;
            if ((uint32_t)(g_Now - g_LastSteps) > 500U)
            {
                VolumeData volume;
                memcpy(&volume, payload, sizeof(VolumeData));
                volume.volume = min((uint8_t)100, volume.volume);
                g_Sessions[(int8_t)command - (int8_t)Command::VOLUME_CURR_CHANGE].data = volume;
            }
        }
        else if (command == Command::MODE_STATES)
        {
            if (payloadLength != sizeof(ModeStates)) return Command::ERROR;
            ModeStates states;
            memcpy(&states, payload, sizeof(ModeStates));
            for (uint8_t mode = 0; mode < DisplayMode::MODE_MAX; ++mode)
            {
                uint8_t maximum = mode == DisplayMode::MODE_GAME ? STATE_GAME_MAX : STATE_MAX;
                if (states.states[mode] >= maximum)
                    states.states[mode] = 0;
            }
            g_ModeStates = states;
        }
        else if (command == Command::TIME_SYNC)
        {
            if (payloadLength != sizeof(TimeData)) return Command::ERROR;
            TimeData time;
            memcpy(&time, payload, sizeof(TimeData));
            if (time.hour > 23 || time.minute > 59 || time.second > 59)
                return Command::ERROR;
            g_TimeData = time;
            g_TimeSyncMillis = g_Now;
            g_TimeValid = true;
        }
        else if (command == Command::METER_LEVEL)
        {
            if (payloadLength != sizeof(MeterData)) return Command::ERROR;
            MeterData meter;
            memcpy(&meter, payload, sizeof(MeterData));
            meter.current = min((uint8_t)100, meter.current);
            meter.alternate = min((uint8_t)100, meter.alternate);
            g_MeterData = meter;
        }
        else if (command == Command::APP_ICON_META)
        {
            if (payloadLength != sizeof(AppIconMeta)) return Command::ERROR;
            AppIconMeta meta;
            memcpy(&meta, payload, sizeof(AppIconMeta));
            Display::ReceiveAppIconMeta(&meta);
        }
        else if (command == Command::APP_ICON_CHUNK)
        {
            if (payloadLength != sizeof(AppIconChunk)) return Command::ERROR;
            AppIconChunk chunk;
            memcpy(&chunk, payload, sizeof(AppIconChunk));
            Display::ReceiveAppIconChunk(&chunk);
        }
        else if (command == Command::DEBUG)
        {
            if (payloadLength != 0) return Command::ERROR;
            // Explicit diagnostics request only; the production stream remains
            // quiet and framed. This allows end-to-end state verification.
            WriteImmediate(Command::SETTINGS);
            WriteImmediate(Command::SESSION_INFO);
            WriteImmediate(Command::CURRENT_SESSION);
            WriteImmediate(Command::ALTERNATE_SESSION);
            WriteImmediate(Command::PREVIOUS_SESSION);
            WriteImmediate(Command::NEXT_SESSION);
            WriteImmediate(Command::MODE_STATES);
            WriteImmediate(Command::METER_LEVEL);
        }
        else
        {
            return Command::ERROR;
        }

        g_HeartbeatTimeout = g_Now + DEVICE_RESET_AFTER_INACTIVTY;
        return command;
    }

    void Initialize(void)
    {
        s_rxLength = 0;
        s_txHead = 0;
        s_txTail = 0;
        s_txCount = 0;
        s_receivedFrames = 0;
        s_transmittedFrames = 0;
        s_crcErrors = 0;
        s_protocolErrors = 0;
        s_lastCommand = Command::NONE;
        s_lastErrorCommand = Command::NONE;
    }

    Command Read(void)
    {
        while (Serial.available())
        {
            if (s_rxLength >= RX_BUFFER_SIZE)
                DiscardRx(1);
            s_rxBuffer[s_rxLength++] = (uint8_t)Serial.read();
        }

        while (s_rxLength >= 2)
        {
            uint16_t magicAt = 0;
            while (magicAt + 1 < s_rxLength &&
                   (s_rxBuffer[magicAt] != FRAME_MAGIC_0 || s_rxBuffer[magicAt + 1] != FRAME_MAGIC_1))
            {
                ++magicAt;
            }

            if (magicAt + 1 >= s_rxLength)
            {
                bool retainFirstMagic = s_rxBuffer[s_rxLength - 1] == FRAME_MAGIC_0;
                s_rxBuffer[0] = FRAME_MAGIC_0;
                s_rxLength = retainFirstMagic ? 1 : 0;
                return Command::NONE;
            }
            if (magicAt > 0)
                DiscardRx(magicAt);
            if (s_rxLength < 6)
                return Command::NONE;

            uint8_t payloadLength = s_rxBuffer[3];
            if (payloadLength > MAX_PAYLOAD)
            {
                ++s_protocolErrors;
                s_lastErrorCommand = Command::ERROR;
                DiscardRx(1);
                continue;
            }

            uint16_t frameLength = (uint16_t)payloadLength + 6U;
            if (s_rxLength < frameLength)
                return Command::NONE;

            uint16_t expected = (uint16_t)s_rxBuffer[4 + payloadLength]
                              | ((uint16_t)s_rxBuffer[5 + payloadLength] << 8);
            uint16_t actual = Crc16(s_rxBuffer + 2, (size_t)payloadLength + 2);
            if (actual != expected)
            {
                ++s_crcErrors;
                s_lastErrorCommand = (Command)(int8_t)s_rxBuffer[2];
                DiscardRx(1);
                continue;
            }

            Command command = (Command)(int8_t)s_rxBuffer[2];
            Command result = ProcessFrame(command, s_rxBuffer + 4, payloadLength);
            ++s_receivedFrames;
            s_lastCommand = command;
            DiscardRx(frameLength);
            if (result != Command::ERROR)
                WriteImmediate(Command::OK);
            else
            {
                ++s_protocolErrors;
                s_lastErrorCommand = command;
            }
            return result;
        }
        return Command::NONE;
    }

    void WriteImmediate(Command command)
    {
        if (command == Command::ERROR || command == Command::NONE || command == Command::DEBUG)
            return;

        if (command == Command::TEST)
        {
            char identity[32];
            int length = snprintf(identity, sizeof(identity), "%s;P=%u", VERSION,
                                  (unsigned)PROTOCOL_VERSION);
            if (length > 0 && length < (int)sizeof(identity))
                SendFrame(command, identity, (uint8_t)length);
        }
        else if (command == Command::SETTINGS)
            SendFrame(command, &g_Settings, sizeof(DeviceSettings));
        else if (command == Command::SESSION_INFO)
            SendFrame(command, &g_SessionInfo, sizeof(SessionInfo));
        else if (command >= Command::CURRENT_SESSION && command <= Command::NEXT_SESSION)
            SendFrame(command, &g_Sessions[(int8_t)command - (int8_t)Command::CURRENT_SESSION], sizeof(SessionData));
        else if (command >= Command::VOLUME_CURR_CHANGE && command <= Command::VOLUME_NEXT_CHANGE)
            SendFrame(command, &g_Sessions[(int8_t)command - (int8_t)Command::VOLUME_CURR_CHANGE].data, sizeof(VolumeData));
        else if (command == Command::MODE_STATES)
            SendFrame(command, &g_ModeStates, sizeof(ModeStates));
        else if (command == Command::METER_LEVEL)
            SendFrame(command, &g_MeterData, sizeof(MeterData));
        else
            SendFrame(command);
    }

    void Write(Command command)
    {
        for (uint8_t i = 0; i < s_txCount; ++i)
        {
            uint8_t index = (s_txTail + i) % TX_QUEUE_SIZE;
            if (s_txQueue[index] == command) return;
        }
        TxEnqueue(command);
    }

    static uint32_t s_lastTxTime = 0;
    static constexpr uint32_t TX_INTERVAL = 30;

    void SendPending(void)
    {
        if (s_txCount == 0 || (uint32_t)(g_Now - s_lastTxTime) < TX_INTERVAL)
            return;

        Command command = TxDequeue();
        if (command != Command::NONE)
        {
            WriteImmediate(command);
            s_lastTxTime = g_Now;
        }
    }

    uint32_t ReceivedFrames(void) { return s_receivedFrames; }
    uint32_t TransmittedFrames(void) { return s_transmittedFrames; }
    uint32_t CrcErrors(void) { return s_crcErrors; }
    uint32_t ProtocolErrors(void) { return s_protocolErrors; }
    Command LastCommand(void) { return s_lastCommand; }
    Command LastErrorCommand(void) { return s_lastErrorCommand; }
}
