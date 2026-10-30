#pragma once
#include "io.h"
#define ISR(vector) void vector(void)
#define cli() (SREG &= (uint8_t)~0x80u)
#define sei() (SREG |= 0x80u)
