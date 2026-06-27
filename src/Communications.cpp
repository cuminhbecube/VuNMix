#include "Communications.h"

// Defined in the main file
extern DeviceSettings g_Settings;
extern SessionInfo g_SessionInfo;
extern SessionData g_Sessions[4];
extern ModeStates g_ModeStates;
extern uint32_t g_HeartbeatTimeout;
extern uint32_t g_Now;
extern uint32_t g_LastSteps;
extern TimeData g_TimeData;
extern uint32_t g_TimeSyncMillis;
extern bool g_TimeValid;

//#define TEST_HARNESS

namespace Communications
{
    // --- Outgoing message queue ---
    // Simple queue: store up to 8 pending outgoing commands.
    // The device can only generate a few commands per loop iteration.
    static const uint8_t TX_QUEUE_SIZE = 8;
    static Command s_txQueue[TX_QUEUE_SIZE];
    static uint8_t s_txHead = 0;
    static uint8_t s_txTail = 0;
    static uint8_t s_txCount = 0;

    static void TxEnqueue(Command cmd) {
        if (s_txCount >= TX_QUEUE_SIZE) return; // drop if full
        s_txQueue[s_txHead] = cmd;
        s_txHead = (s_txHead + 1) % TX_QUEUE_SIZE;
        s_txCount++;
    }

    static Command TxDequeue() {
        if (s_txCount == 0) return Command::NONE;
        Command cmd = s_txQueue[s_txTail];
        s_txTail = (s_txTail + 1) % TX_QUEUE_SIZE;
        s_txCount--;
        return cmd;
    }

    static bool ReadPayload(void *dest, size_t len) {
        return Serial.readBytes(reinterpret_cast<char *>(dest), len) == len;
    }

    void Initialize(void)
    {
        // Serial.begin() is already called in setup() for USB CDC.
        // Do NOT call it again here - it can reset the USB CDC state on ESP32-S3.
        Serial.setTimeout(SERIAL_TIMEOUT);
        s_txHead = 0;
        s_txTail = 0;
        s_txCount = 0;
    }

    Command Read(void)
    {
        Command command = Command::NONE;
        if (Serial.available())
        {
            g_HeartbeatTimeout = g_Now + DEVICE_RESET_AFTER_INACTIVTY;
            command = (Command)Serial.read();
            if (command == Command::TEST)
                WriteImmediate(command);
            else if (command == Command::SETTINGS)
            {
                DeviceSettings temp;
                if (ReadPayload(&temp, sizeof(DeviceSettings)))
                    g_Settings = temp;
                else
                    command = Command::ERROR;
            }
            else if (command == Command::SESSION_INFO)
            {
                SessionInfo temp;
                if (ReadPayload(&temp, sizeof(SessionInfo)))
                    g_SessionInfo = temp;
                else
                    command = Command::ERROR;
            }
            else if (command >= Command::CURRENT_SESSION && command <= Command::NEXT_SESSION)
            {
                SessionData temp;
                if (ReadPayload(&temp, sizeof(SessionData)))
                    g_Sessions[(int8_t)command - (int8_t)Command::CURRENT_SESSION] = temp;
                else
                    command = Command::ERROR;
            }
            else if (command >= Command::VOLUME_CURR_CHANGE && command <= Command::VOLUME_NEXT_CHANGE)
            {
                VolumeData temp;
                if (ReadPayload(&temp, sizeof(VolumeData))) {
                    // Anti-echo debounce: if the user turned the knob locally within the last 500ms,
                    // ignore volume updates from the PC to prevent the volume from bouncing back and forth.
                    // This prevents the PC's audio event loop from overwriting our local changes with stale values.
                    if (g_Now - g_LastSteps > 500) {
                        g_Sessions[(int8_t)command - (int8_t)Command::VOLUME_CURR_CHANGE].data = temp;
                    }
                } else {
                    command = Command::ERROR;
                }
            }
            else if (command == Command::MODE_STATES)
            {
                ModeStates temp;
                if (ReadPayload(&temp, sizeof(ModeStates)))
                    g_ModeStates = temp;
                else
                    command = Command::ERROR;
            }
            else if (command == Command::TIME_SYNC)
            {
                TimeData temp;
                if (ReadPayload(&temp, sizeof(TimeData))) {
                    g_TimeData = temp;
                    g_TimeSyncMillis = g_Now;
                    g_TimeValid = true;
                } else {
                    command = Command::ERROR;
                }
            }
#ifdef TEST_HARNESS
            else if (command == Command::DEBUG)
            {
                WriteImmediate(Command::SETTINGS);
                WriteImmediate(Command::SESSION_INFO);
                WriteImmediate(Command::CURRENT_SESSION);
                WriteImmediate(Command::ALTERNATE_SESSION);
                WriteImmediate(Command::PREVIOUS_SESSION);
                WriteImmediate(Command::NEXT_SESSION);
                WriteImmediate(Command::VOLUME_CURR_CHANGE);
                WriteImmediate(Command::VOLUME_ALT_CHANGE);
                WriteImmediate(Command::VOLUME_PREV_CHANGE);
                WriteImmediate(Command::VOLUME_NEXT_CHANGE);
            }
#endif
            // Reply OK only after a complete command payload was consumed.
            if (command != Command::ERROR)
                WriteImmediate(Command::OK);
        }
        return command;
    }

    void WriteImmediate(Command command)
    {
        if (command == Command::ERROR || command == Command::NONE || command == Command::DEBUG)
            return;

        if (command == Command::TEST)
        {
            Serial.write((uint8_t)command);
            Serial.println(F(VERSION));
            Serial.flush();
            return;
        }

        uint8_t buf[33];
        buf[0] = (uint8_t)command;
        size_t len = 1;

        if (command == Command::SETTINGS) {
            memcpy(&buf[len], (char *)&g_Settings, sizeof(DeviceSettings));
            len += sizeof(DeviceSettings);
        }
        else if (command == Command::SESSION_INFO) {
            memcpy(&buf[len], (char *)&g_SessionInfo, sizeof(SessionInfo));
            len += sizeof(SessionInfo);
        }
        else if (command >= Command::CURRENT_SESSION && command <= Command::NEXT_SESSION) {
            memcpy(&buf[len], (char *)&g_Sessions[(int8_t)command - (int8_t)Command::CURRENT_SESSION], sizeof(SessionData));
            len += sizeof(SessionData);
        }
        else if (command >= Command::VOLUME_CURR_CHANGE && command <= Command::VOLUME_NEXT_CHANGE) {
            memcpy(&buf[len], (char *)&g_Sessions[(int8_t)command - (int8_t)Command::VOLUME_CURR_CHANGE].data, sizeof(VolumeData));
            len += sizeof(VolumeData);
        }
        else if (command == Command::MODE_STATES) {
            memcpy(&buf[len], (char *)&g_ModeStates, sizeof(ModeStates));
            len += sizeof(ModeStates);
        }

        Serial.write(buf, len);
        Serial.flush();
    }

    // Write: queues a command to be sent AFTER Read() has finished its OK response.
    // This prevents interleaving device-initiated messages with protocol responses.
    void Write(Command command)
    {
        // Prevent duplicate commands in the queue.
        // Since WriteImmediate always sends the current global state (g_Sessions),
        // having the command in the queue once is sufficient to send the latest data.
        for (uint8_t i = 0; i < s_txCount; i++) {
            uint8_t idx = (s_txTail + i) % TX_QUEUE_SIZE;
            if (s_txQueue[idx] == command) return;
        }
        TxEnqueue(command);
    }

    // Rate-limit transmissions to the PC to avoid overflowing the desktop app's polling loop
    static uint32_t s_lastTxTime = 0;
    static const uint32_t TX_INTERVAL = 30; // Max 1 message per 30ms (~33Hz)

    // SendPending: called from main loop AFTER Read(). Drains the TX queue.
    void SendPending(void)
    {
        if (s_txCount == 0) return;
        
        // Ensure we don't send device-initiated messages too fast
        if (g_Now - s_lastTxTime < TX_INTERVAL) return;

        Command cmd = TxDequeue();
        if (cmd != Command::NONE) {
            WriteImmediate(cmd);
            s_lastTxTime = g_Now;
        }
    }

} // namespace Communications
