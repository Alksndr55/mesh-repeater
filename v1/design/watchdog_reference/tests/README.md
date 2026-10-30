# Firmware logic regression checks

The harness includes the real `main.c`, with AVR headers replaced by small host
register mocks. It checks the waiting/reset transitions, hardware timer restart
on a heartbeat, and an edge injected exactly when PB0 is released. The model
implements write-one-to-clear flags so that clearing a new PCINT is observable.
It also checks stuck-high timeout, falling-edge rearming, repeated heartbeats,
coalesced falling/rising edges, an input queued at the deadline, and rejection
of pulses wholly inside reset.

Windows, with a C++17 compiler already installed:

```powershell
.\tests\run.ps1 -Cxx 'C:\path\to\clang++.exe'
# GCC g++ and Zig are also accepted.
```

Other hosts:

```sh
c++ -std=c++17 -Wall -Wextra -Werror -Itests/include tests/test_firmware.cpp -o /tmp/watchdog-test
/tmp/watchdog-test
```

This is a logic test, not a cycle-accurate AVR simulator. It does not prove actual
oscillator frequency, pin thresholds, pulse width detection, BOD behaviour,
power-on waveforms, or current consumption; those require the board tests in the
main README. Mock interrupt calls represent hardware event delivery; real AVR
vector timing and the WDT four-cycle write sequence must be checked separately
in the compiled firmware.

Baseline (before the fixes, 2026-10-29): two checks failed: hardware WDT phase was
not restarted by a heartbeat; an edge injected immediately after reset release
was erased. The original firmware is retained in a local backup outside this published repository.

After the fixes: all 19 checks pass. The host build uses `-Wall -Wextra -Werror`.
