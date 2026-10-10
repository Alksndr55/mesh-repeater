MCU       := attiny13a
PROGRAMMER ?= usbasp
PORT      ?=
F_CPU     := 128000UL

CC        := avr-gcc
OBJCOPY   := avr-objcopy
AVRDUDE   := avrdude

CFLAGS    := -std=gnu11 -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -Wall -Wextra \
              -ffunction-sections -fdata-sections
LDFLAGS   := -mmcu=$(MCU) -Wl,--gc-sections

all: watchdog.hex watchdog.elf watchdog.map

watchdog.elf: main.o
	$(CC) $(LDFLAGS) -Wl,-Map=$(@:.elf=.map) -o $@ $^

watchdog.hex: watchdog.elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

main.o: main.c
	$(CC) $(CFLAGS) -c -o $@ $<

size: watchdog.elf
	avr-size -C --mcu=$(MCU) $<

# S4.3 carrier integration profile; original firmware/HEX is unchanged.
# HFUSE=0xFB: RESET enabled, DWEN disabled, BODLEVEL=01 (2.7 V).
# LFUSE=0x7B: SPIEN enabled, WDTON disabled, CKDIV8 off,
#             SUT=10 (64 ms reset delay), CKSEL=11 (internal 128 kHz).
# BOD monitors SYS_3V3, not BAT. Additional sleep current needs measurement.
# Slow ISP clock is also required after the 128 kHz clock fuse is applied.
ISP_BITCLOCK_US ?= 100
fuses:
	$(AVRDUDE) -p t13 -c $(PROGRAMMER) $(if $(PORT),-P $(PORT),) -B $(ISP_BITCLOCK_US) \
		-U lfuse:w:0x7B:m -U hfuse:w:0xFB:m

flash: watchdog.hex
	$(AVRDUDE) -p t13 -c $(PROGRAMMER) $(if $(PORT),-P $(PORT),) -B $(ISP_BITCLOCK_US) \
		-U flash:w:$<:i

clean:
	$(RM) main.o watchdog.elf watchdog.hex watchdog.map

.PHONY: all size fuses flash clean
