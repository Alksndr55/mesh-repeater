#pragma once
inline unsigned mock_wdt_restarts;
#define wdt_reset() (++mock_wdt_restarts)
