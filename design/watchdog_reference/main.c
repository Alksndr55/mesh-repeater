#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <avr/wdt.h>
#include <stdint.h>

#ifndef F_CPU
#define F_CPU 128000UL
#endif

/* Physical pins: pin 2 = PB3/PCINT3 input, pin 5 = PB0 reset output. */
#define INPUT_BIT          PB3
#define RESET_OUT_BIT      PB0
#define UNUSED_PULLUPS     ((uint8_t)((1u << PB1) | (1u << PB2) | (1u << PB4)))

/* WDT oscillator is used as the only time base. 8 s * 1350 = 3 h nominal. */
#define WDT_8S_CONFIG       ((uint8_t)((1u << WDP3) | (1u << WDP0)))
/* 1 s: WDP[3:0] = 0110. */
#define WDT_1S_CONFIG       ((uint8_t)((1u << WDP2) | (1u << WDP1)))
#define WATCHDOG_TICKS      ((uint16_t)1350u)

typedef enum {
    STATE_WAITING = 0,
    STATE_RESET_PULSE = 1
} watchdog_state_t;

static volatile uint16_t elapsed_8s_ticks;
static volatile watchdog_state_t state;

static void wdt_configure(uint8_t config)
{
    uint8_t saved_sreg = SREG;

    cli();
    wdt_reset();

    /* Timed sequence required by WDTCR.WDCE (datasheet section 8.4). */
    WDTCR = (uint8_t)((1u << WDCE) | (1u << WDE));
    /* Within four CPU cycles: WDE=0, WDTIE=1, and the requested prescaler. */
    WDTCR = (uint8_t)(config | (1u << WDTIE));

    SREG = saved_sreg;
}

static void reset_output_release(void)
{
    /* PORTB0 remains zero; changing DDRB to input makes the open-drain node Hi-Z. */
    DDRB &= (uint8_t)~(1u << RESET_OUT_BIT);
    PORTB &= (uint8_t)~(1u << RESET_OUT_BIT);
}

static void reset_output_assert(void)
{
    /* PORTB0 is already zero, so enabling the output can only assert a low level. */
    PORTB &= (uint8_t)~(1u << RESET_OUT_BIT);
    DDRB |= (uint8_t)(1u << RESET_OUT_BIT);
}

static void enter_reset_pulse(void)
{
    state = STATE_RESET_PULSE;
    elapsed_8s_ticks = 0;

    /* Ignore input changes while reset is asserted. */
    GIMSK &= (uint8_t)~(1u << PCIE);
    GIFR |= (uint8_t)(1u << PCIF);

    reset_output_assert();
    wdt_configure(WDT_1S_CONFIG);
}

static void finish_reset_pulse(void)
{
    reset_output_release();
    elapsed_8s_ticks = 0;
    wdt_configure(WDT_8S_CONFIG);

    GIFR |= (uint8_t)(1u << PCIF);
    GIMSK |= (uint8_t)(1u << PCIE);
    state = STATE_WAITING;
}

ISR(PCINT0_vect)
{
    /* PCINT is asynchronous and wakes the MCU from Power-down.  Accept only a
       sampled high level, so the falling edge of a pulse is ignored. */
    if ((PINB & (1u << INPUT_BIT)) != 0u) {
        elapsed_8s_ticks = 0;
    }
}

ISR(WDT_vect)
{
    if (state == STATE_WAITING) {
        if (elapsed_8s_ticks < WATCHDOG_TICKS) {
            ++elapsed_8s_ticks;
        }
        if (elapsed_8s_ticks >= WATCHDOG_TICKS) {
            enter_reset_pulse();
        }
    } else {
        /* One nominal 1 s WDT period has elapsed. */
        finish_reset_pulse();
    }
}

static void io_and_peripheral_init(void)
{
    /* All pins start as inputs with pull-ups off.  PB0 is released (Hi-Z). */
    DDRB = 0u;
    PORTB = 0u;

    /* Unused GPIO pins are biased high to avoid floating inputs. */
    PORTB |= UNUSED_PULLUPS;

    /* PB3 is the active-high watchdog input; an external 100 kOhm pulldown
       defines the inactive level, so the internal pull-up stays disabled. */
    PORTB &= (uint8_t)~(1u << INPUT_BIT);
    reset_output_release();

    /* No ADC, comparator, or Timer/Counter0 is needed. */
    ADCSRA &= (uint8_t)~(1u << ADEN);
    ACSR |= (uint8_t)(1u << ACD);
    PRR = (uint8_t)((1u << PRTIM0) | (1u << PRADC));

    /* Power-down: only asynchronous PCINT and WDT can wake the MCU. */
    MCUCR = (uint8_t)(1u << SM1);

    PCMSK = (uint8_t)(1u << PCINT3);
    GIFR |= (uint8_t)(1u << PCIF);
    GIMSK |= (uint8_t)(1u << PCIE);
}

int main(void)
{
    cli();

    /* Clear reset flags before configuring the interrupt-mode watchdog. */
    MCUSR = 0u;
    io_and_peripheral_init();
    state = STATE_WAITING;
    elapsed_8s_ticks = 0u;
    wdt_configure(WDT_8S_CONFIG);

    set_sleep_mode(SLEEP_MODE_PWR_DOWN);
    sei();

    for (;;) {
        sleep_enable();
        sei();
        sleep_cpu();
        sleep_disable();
    }
}
