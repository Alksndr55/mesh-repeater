#pragma once
#include <stdint.h>

/* Host register model: storage, write-one-to-clear flags, and a write hook. */
struct MockRegister {
    uint8_t value = 0;
    uint8_t w1c = 0;
    void (*after_write)(uint8_t, uint8_t) = nullptr;
    operator uint8_t() const { return value; }
    MockRegister &operator=(uint8_t rhs) {
        uint8_t old = value;
        value = (uint8_t)(((value & w1c) & ~rhs) | (rhs & ~w1c));
        if (after_write) after_write(old, value);
        return *this;
    }
    MockRegister &operator|=(uint8_t rhs) { return *this = (uint8_t)(value | rhs); }
    MockRegister &operator&=(uint8_t rhs) { return *this = (uint8_t)(value & rhs); }
};
inline MockRegister DDRB, PORTB, PINB, WDTCR, GIFR, GIMSK, PCMSK;
inline MockRegister ADCSRA, ACSR, PRR, MCUCR, MCUSR, BODCR, DIDR0;
inline uint8_t SREG;
enum { PB0=0, PB1=1, PB2=2, PB3=3, PB4=4, PB5=5,
       PCINT3=3, PCIF=5, PCIE=5, WDP0=0, WDP1=1, WDP2=2,
       WDE=3, WDCE=4, WDP3=5, WDTIE=6, WDTIF=7,
       ADEN=7, ACD=7, PRTIM0=1, PRADC=0, SM1=4,
       BODS=1, BODSE=0, SE=5, WDRF=3 };
#define _BV(bit) (1u << (bit))
