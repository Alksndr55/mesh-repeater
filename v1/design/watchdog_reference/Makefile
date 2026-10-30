MCU       := attiny13a
PROGRAMMER ?= usbasp
PORT      ?=
F_CPU     := 128000UL
ISP_BITCLOCK_US ?= 100
LFUSE     ?= 0x73
HFUSE     ?= 0xFB

CC        := avr-gcc
OBJCOPY   := avr-objcopy
AVRDUDE   := avrdude

CFLAGS    := -std=gnu11 -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -Wall -Wextra -Werror \
              -ffunction-sections -fdata-sections
LDFLAGS   := -mmcu=$(MCU) -Wl,--gc-sections

all: watchdog.hex watchdog.map

# The linker writes both ELF and MAP. Force that single recipe when MAP was
# removed, and make every MAP request wait for ELF (also safe with make -j).
watchdog.elf: main.o $(if $(wildcard watchdog.map),,FORCE_LINK)
	$(CC) $(LDFLAGS) -Wl,-Map=$(@:.elf=.map) -o $@ main.o

watchdog.map: watchdog.elf

watchdog.hex: watchdog.elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

main.o: main.c
	$(CC) $(CFLAGS) -c -o $@ $<

size: watchdog.elf
	avr-size -C --mcu=$(MCU) $<

# Fuse values for the design:
# HFUSE=0xFB: RESET enabled, DWEN disabled, BOD=2.7 V (also in sleep).
# LFUSE=0x73: SPIEN enabled, WDTON disabled, CKDIV8 off,
#             SUT=00, CKSEL=11 (internal 128 kHz oscillator).
fuses:
	$(AVRDUDE) -p t13 -c $(PROGRAMMER) -B $(ISP_BITCLOCK_US) $(if $(PORT),-P $(PORT),) \
		-U lfuse:w:$(LFUSE):m -U hfuse:w:$(HFUSE):m

flash: watchdog.hex
	$(AVRDUDE) -p t13 -c $(PROGRAMMER) -B $(ISP_BITCLOCK_US) $(if $(PORT),-P $(PORT),) \
		-U flash:w:$<:i

# Keep flash and fuse writes sequential even when invoked as make -j program.
program: flash
	$(MAKE) fuses

clean:
	-del /Q main.o watchdog.elf watchdog.hex watchdog.map 2>NUL

.PHONY: all size fuses flash program clean FORCE_LINK

.DELETE_ON_ERROR:
