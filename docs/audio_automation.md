# VuNMix audio routing and ducking

VuNMix v0.7 adds an optional audio-automation layer. It does not change the
ESP32 protocol: routing and ducking run entirely on Windows.

## Configuration file

Rules are stored atomically in:

`%LOCALAPPDATA%\VuNMix\audio_automation.json`

The tray menu **Audio Automation → Open automation rules** opens this file.
Routing and ducking can also be enabled/disabled independently from the tray.

The first launch creates a safe empty configuration, so upgrading VuNMix never
silently moves or attenuates an application.

## Per-application output routing

Routing is supported on Windows 10 1803 (build 17134) and later. VuNMix uses the
`Windows.Media.Internal.AudioPolicyConfig` factory used by the Windows Volume
Mixer / EarTrumpet approach. Builds before 21390 use the downlevel interface;
21390+ uses the newer interface variant.

Example:

```json
{
  "routing_enabled": true,
  "routing_rules": [
    {
      "name": "Discord to headset",
      "app_pattern": "discord*",
      "device_pattern": "USB Headset",
      "enabled": true
    },
    {
      "name": "Games to DAC",
      "app_pattern": "game",
      "device_pattern": "USB DAC",
      "enabled": true
    }
  ]
}
```

Rules are evaluated in order. The first matching rule for a process wins.
`app_pattern` and `device_pattern` are case-insensitive; `*`, `?`, and `[]`
wildcards are supported. A plain string also performs a practical substring
match. Disabling routing clears overrides that VuNMix applied during the current
run.

## Audio ducking

A ducking rule watches the peak meter of one application and reduces one or
more target applications while the trigger is audible.

```json
{
  "ducking_enabled": true,
  "ducking_rules": [
    {
      "name": "Voice ducks music",
      "trigger_pattern": "discord",
      "target_patterns": ["spotify", "vlc"],
      "reduction_percent": 50,
      "threshold": 0.02,
      "attack_ms": 150,
      "release_ms": 650,
      "enabled": true
    }
  ]
}
```

`threshold` is a normalized WASAPI peak from `0.0` to `1.0`. If multiple active
rules target the same application, the strongest reduction wins.

### Manual changes while ducking

VuNMix remembers the last volume it wrote. If the target changes to another
value while ducking, that is treated as a manual/user change instead of being
fought by the automation. VuNMix infers a new unducked baseline from that value,
then releases to the new baseline.

### Crash / restart recovery

Before changing a target, VuNMix writes its original volume/mute state and the
last automation-applied value into the same atomic configuration file. On the
next start:

- if the session is still at the value VuNMix applied, the original volume is
  restored;
- if the current value is different, VuNMix assumes the user changed it after
  the crash and discards the stale journal without overwriting the user value.

A clean exit restores every currently ducked target before shutting down.

## Notes

Per-app routing relies on a Windows internal COM/WinRT audio-policy interface.
It is capability checked by OS build and isolated from the rest of the mixer;
a routing failure does not stop volume control, profiles, media, OBS, or the
ESP32 connection.
