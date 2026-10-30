/* Tests the actual firmware C source with host register mocks.
   This is NOT a clock-accurate AVR or electrical simulation. */
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#define main firmware_main
#ifndef FIRMWARE_SOURCE
#define FIRMWARE_SOURCE "../main.c"
#endif
#include FIRMWARE_SOURCE
#undef main

static unsigned failures;
static void check(bool condition, const char *name)
{
    std::printf("%s %s\n", condition ? "PASS" : "FAIL", name);
    if (!condition) ++failures;
}

static void input(bool high)
{
    uint8_t next = high ? (1u << INPUT_BIT) : 0;
    if (next != PINB.value && (PCMSK.value & (1u << PCINT3)))
        GIFR.value |= (1u << PCIF);
    PINB.value = next;
}

static void serve_input()
{
    if ((GIFR.value & GIMSK.value & (1u << PCIF)) == 0) return;
    GIFR.value &= (uint8_t)~(1u << PCIF);
    cli();
    PCINT0_vect();
    sei();
}

static void tick()
{
    if (!(WDTCR.value & (1u << WDTIE))) return;
    WDTCR.value &= (uint8_t)~(1u << WDTIF);
    cli();
    WDT_vect();
    sei();
}

static void setup()
{
    for (auto reg : {&DDRB, &PORTB, &PINB, &WDTCR, &GIFR, &GIMSK,
                    &PCMSK, &ADCSRA, &ACSR, &PRR, &MCUCR, &MCUSR,
                    &BODCR, &DIDR0}) {
        reg->value = 0;
        reg->w1c = 0;
        reg->after_write = nullptr;
    }
    GIFR.w1c = (1u << PCIF);
    WDTCR.w1c = (1u << WDTIF);
    SREG = 0;
    mock_wdt_restarts = 0;
    io_and_peripheral_init();
    state = STATE_WAITING;
    elapsed_8s_ticks = 0;
    input_high_seen = 0;
    wdt_configure(WDT_8S_CONFIG);
    sei();
}

static void edge_on_release(uint8_t old, uint8_t next)
{
    if ((old & (1u << RESET_OUT_BIT)) && !(next & (1u << RESET_OUT_BIT)))
        input(true);
}

int main()
{
    setup();
    check(!(DDRB.value & (1u << RESET_OUT_BIT)) &&
          !(PORTB.value & (1u << RESET_OUT_BIT)), "startup releases PB0 without push-pull high");
    for (unsigned i = 0; i < WATCHDOG_TICKS - 1; ++i) tick();
    check(state == STATE_WAITING, "no reset before full interval");
    tick();
    check(state == STATE_RESET_PULSE && (DDRB.value & (1u << RESET_OUT_BIT)),
          "full interval asserts reset");
    input(true);
    serve_input();
    check(state == STATE_RESET_PULSE, "input cannot terminate reset pulse");
    input(false);
    tick();
    check(state == STATE_WAITING && elapsed_8s_ticks == 0 &&
          !(DDRB.value & (1u << RESET_OUT_BIT)), "reset completion starts full new interval");
    for (unsigned i = 0; i < WATCHDOG_TICKS - 1; ++i) tick();
    check(state == STATE_WAITING, "new interval is not shortened by preceding reset");

    setup();
    elapsed_8s_ticks = 12;
    unsigned before = mock_wdt_restarts;
    input(true);
    serve_input();
    check(elapsed_8s_ticks == 0, "rising input refreshes software deadline");
    check(mock_wdt_restarts > before, "rising input restarts hardware WDT phase");
    elapsed_8s_ticks = 5;
    input(false);
    serve_input();
    check(elapsed_8s_ticks == 5, "falling input does not refresh deadline");

    setup();
    enter_reset_pulse();
    before = mock_wdt_restarts;
    tick();
    unsigned baseline_release_restarts = mock_wdt_restarts - before;
    setup();
    enter_reset_pulse();
    DDRB.after_write = edge_on_release;
    before = mock_wdt_restarts;
    tick();
    serve_input();
    check(mock_wdt_restarts - before > baseline_release_restarts,
          "edge immediately after PB0 release is consumed rather than erased");

    setup();
    input(true);
    serve_input();
    before = mock_wdt_restarts;
    for (unsigned i = 0; i < WATCHDOG_TICKS - 1; ++i) tick();
    check(state == STATE_WAITING && mock_wdt_restarts == before,
          "held-high input is accepted once and does not feed on every tick");
    tick();
    check(state == STATE_RESET_PULSE, "held-high input eventually triggers reset");

    setup();
    for (unsigned pulse = 0; pulse < 20; ++pulse) {
        for (unsigned i = 0; i < 100; ++i) tick();
        input(true);
        serve_input();
        input(false);
        serve_input();
    }
    check(state == STATE_WAITING && elapsed_8s_ticks == 0,
          "repeated pulses and falling-edge rearming prevent reset");

    setup();
    elapsed_8s_ticks = WATCHDOG_TICKS - 1;
    input(true); /* PCINT queued while the WDT handler starts. */
    tick();
    check(state == STATE_WAITING && elapsed_8s_ticks == 0,
          "new high visible at the final tick wins over timeout");
    serve_input();
    check(state == STATE_WAITING && elapsed_8s_ticks == 0,
          "pending PCINT after deadline sampling leaves a full new interval");

    setup();
    input(true);
    serve_input();
    elapsed_8s_ticks = 7;
    before = mock_wdt_restarts;
    input(false);
    input(true); /* Both edges arrive before the pending PCINT can execute. */
    serve_input();
    check(elapsed_8s_ticks == 0 && mock_wdt_restarts > before,
          "coalesced falling/rising edges still accept the new high");

    setup();
    elapsed_8s_ticks = WATCHDOG_TICKS - 1;
    WDTCR.value |= (1u << WDTIF);
    input(true);
    serve_input();
    check(!(WDTCR.value & (1u << WDTIF)) && elapsed_8s_ticks == 0,
          "accepted pulse clears an old pending WDT tick");

    setup();
    enter_reset_pulse();
    before = mock_wdt_restarts;
    input(true);
    serve_input();
    input(false);
    serve_input();
    check(mock_wdt_restarts == before && state == STATE_RESET_PULSE,
          "pulse wholly inside reset does not restart its duration");
    tick();
    check(!(GIFR.value & (1u << PCIF)) && elapsed_8s_ticks == 0,
          "stale reset-window input flag is discarded before reception resumes");

    std::printf("%u failure(s)\n", failures);
    return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
