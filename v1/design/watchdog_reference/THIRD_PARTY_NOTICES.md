# Attribution and licence scope

Firmware, build scripts, register-mock tests and authored documentation originate
from Alksndr55 / @Alksndritm, watchdog v1.00, and retain CC BY-NC-SA 4.0.
The complete licence is in LICENSE.md. The board integration notes and the
100 us ISP default in Makefile are the Mesh Repeater integration profile.

Canonical source: https://github.com/Alksndr55/watchdog/releases/tag/v1.00
Local workspace origin: ../../../watchdog, relative to this directory.
The manufacturer datasheet is available in that canonical project; it is not
copied into this integration directory and retains the manufacturer terms.

AVR GCC, AVR Libc, AVR Binutils and Zig are external tools and are not included.
The headers under tests/include/avr are project register mocks, not AVR Libc.
