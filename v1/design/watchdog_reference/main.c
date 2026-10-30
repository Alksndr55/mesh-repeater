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

/* WDT is the only time base. The "8 s" setting is 1048576 oscillator cycles;
   1350 periods give about 3.5 h on the datasheet's typical 3.3 V curves. */
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
static volatile uint8_t input_high_seen;

static void wdt_configure(uint8_t config)
{
    uint8_t saved_sreg = SREG;

    cli();
    wdt_reset();

    /* Timed sequence required by WDTCR.WDCE (datasheet section 8.4). */
    WDTCR = (uint8_t)((1u << WDCE) | (1u << WDE));
    /* Within four CPU cycles: WDE=0, WDTIE=1, and the requested prescaler. */
    WDTCR = (uint8_t)(config | (1u << WDTIE) | (1u << WDTIF));

    SREG = saved_sreg;
}

/* Called only with interrupts disabled (initialization or an ISR). Clearing
   a queued WDT interrupt prevents an old tick from shortening a new interval. */
static void restart_wait_interval(void)
{
    elapsed_8s_ticks = 0u;
    wdt_reset();
    WDTCR |= (uint8_t)(1u << WDTIF);
}

/* The timer may sample a previously unseen high, but must never repeatedly
   feed on a stuck-high input. PCINT handles actual input changes separately. */
static uint8_t sample_input_level(void)
{
    if ((PINB & (1u << INPUT_BIT)) == 0u) {
        input_high_seen = 0u;
    } else if (input_high_seen == 0u) {
        input_high_seen = 1u;
        restart_wait_interval();
        return 1u;
    }
    return 0u;
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
    GIFR = (uint8_t)(1u << PCIF);

    reset_output_assert();
    wdt_configure(WDT_1S_CONFIG);
}

static void finish_reset_pulse(void)
{
    /* Prepare reception while PB0 is still asserted. Never clear PCIF after
       releasing PB0: that would erase a new post-reset rising edge. */
    elapsed_8s_ticks = 0u;
    input_high_seen = 0u;
    wdt_configure(WDT_8S_CONFIG);
    state = STATE_WAITING;
    GIFR = (uint8_t)(1u << PCIF);
    GIMSK |= (uint8_t)(1u << PCIE);
    reset_output_release();
    restart_wait_interval();
    /* Also accept a high which began during reset and is still present. */
    (void)sample_input_level();
}

ISR(PCINT0_vect)
{
    /* Asynchronous PCINT wakes from Power-down on both edges. A falling edge
       only re-arms reception; it does not feed the watchdog. */
    if (state == STATE_WAITING) {
        if ((PINB & (1u << INPUT_BIT)) != 0u) {
            /* Accept even if a short low followed by a high coalesced into one
               PCIF while another ISR was running. A static high has no edges. */
            input_high_seen = 1u;
            restart_wait_interval();
        } else {
            input_high_seen = 0u;
        }
    }
}

ISR(WDT_vect)
{
    if (state == STATE_WAITING) {
        /* A new high visible at this decision point wins over the timeout.
           Once reset is committed, later input belongs to the reset window. */
        if (sample_input_level() != 0u) {
            return;
        }
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
    GIFR = (uint8_t)(1u << PCIF);
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
    input_high_seen = 0u;
    wdt_configure(WDT_8S_CONFIG);
    (void)sample_input_level();

    set_sleep_mode(SLEEP_MODE_PWR_DOWN);
    for (;;) {
        cli();
        sleep_enable();
        /* BOD remains enabled in Power-down (HFUSE=0xFB). */
        sei();
        sleep_cpu();
        sleep_disable();
    }
}
