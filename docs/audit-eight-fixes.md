# Long-running audit fixes

The eight reported findings are addressed on `fix/audit-eight-issues`.

| Finding | Change | Regression coverage |
| --- | --- | --- |
| Worker accumulation during reconnect/restart | Coalesce initial audio enumeration across connection tokens. Give heartbeat, audio sync, VU, profile, artwork and automation workers an immutable cancellation event for each start. Retain blocked workers and defer replacement until they finish. Coalesce automation cleanup and interrupt weather waits. | 200 reconnect tokens share one blocked enumeration; 200 replacement requests retain one old worker and launch one replacement after it exits. |
| Audio operations applied to the wrong item after refresh | Pass captured AudioItem identities to volume, default-device, volume-read and meter operations. Resolve endpoint/session identities under the audio COM lock; return failure if the target disappears. | Reordered and deleted session identities; native endpoint volume/read/meter/default-device regression. |
| Recovery of currently active ducking corrupts baseline | Exclude active duck states from crash recovery. Recover a returning session before creating its next duck state. | 80 -> 40 -> recovery check -> 40 -> release 80. |
| Vanished duck sessions grow indefinitely | Remove vanished active states immediately. Retain at most 256 missing recovery records, with a 30-second grace period. | 300 unique vanished sessions stay bounded and expire. |
| Unchanged ducking repeatedly writes/fsyncs JSON | Skip unchanged recovery records and identical saved snapshots. Serialize snapshots and replacements; persist changed volume intent before applying it. Keep immediate persistence for actual changes. | 100 steady ticks and recovery checks cause zero fsyncs; a fresh service still restores the recorded baseline. |
| VU retains a meter for an old session at the same index | Include native endpoint/session identity in the meter selection key and pass the captured target during meter creation. Close replaced meters. | Index 0 changes from A to B: both meters are created and closed. |
| Desktop icon cache outlives the firmware's eight slots | Mirror the firmware's eight-entry FIFO, serialize send/bookkeeping, and resend evicted artwork even when its digest is unchanged. | Sending nine icons evicts the first; returning to it sends it again. |
| A failed automatic firmware lookup suppresses future attempts | Record the attempt only after a successful lookup; retry failures and missing assets through one daemon timer with 60s to 900s exponential backoff. Respect shutdown, connection and configuration checks. | Failed lookup remains retryable; retries coalesce into one timer; successful lookup prevents repeated dispatch. |

## Validation

Windows CI runs the complete unit-test suite, five isolated connection stress runs, firmware compilation, PyInstaller packaging, packaged esptool verification and installer compilation. Local platform-independent tests additionally exercise the failure and cancellation scenarios above. Windows-only native audio tests require a Windows runner.

A multi-hour run with the user's audio devices, players and USB hardware is still needed to measure real RAM/handle usage. Regression simulations establish bounded ownership and correct state transitions; they do not establish a numeric RAM ceiling on a real machine.
