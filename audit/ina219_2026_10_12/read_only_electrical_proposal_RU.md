# INA219: read-only electrical proposal, 2026-10-12

No native CAD, canonical model, BOM, firmware or accepted LTO protection was changed by this review.

## Recommended topology

J8.1 and J12.1 become BAT_RAW. A single battery current shunt connects BAT_RAW to existing system BAT. Both connectors must be on the same raw side; otherwise one battery option bypasses the shunt. Main charger and TPS63802 remain on the system BAT side. C4, C12, C13, C52 and C53 remain system-side bypass. Retain the existing direct copper feed through C53.1. Keep the original CN3722 R1 = 0.28 ohm current-control shunt; INA219 shunt is a separate measurement function.

For an explicit positive-charge convention, INA IN+ senses system BAT and IN- senses BAT_RAW through short Kelvin traces. Then Bus Voltage is actual battery voltage, charging current positive and discharge current negative. Reverse the sense assignment only if firmware reconstructs battery voltage as Vbus + Vshunt. Keep upper BAT_ADC divider fed from BAT_RAW via the interboard battery-sense contact. TP1 may become BAT_RAW; document that decision. Keeping CN3722 R3/C30 feedback on system BAT preserves the established charger circuit and causes only I_charge*R_shunt battery-side under-voltage, falling toward zero on taper; do not silently move the compensation loop across the new shunt. R15 EN sense should be explicitly chosen: BAT_RAW preserves the intended battery cutoff, system BAT cuts off slightly earlier under discharge. Both stay safely above TPS63802 minimum operating voltage for the project load.

Keep top LTO balance branch R47.1 on BAT_RAW and the mid/bottom branches unchanged. This preserves true cell voltages and accepted original balance behavior. INA cannot measure the lower-cell balancing current from LTO_MID to GND; with both balances directly at the cell taps neither local balancing branch passes the main positive shunt. Telemetry therefore measures external pack charge/discharge current, not all cell bleed consumption or a guaranteed state-of-charge/coulomb counter.

## Device and power seam

Preferred INA219BIDR, SOIC-8, LCSC C2155799, for lower offset than A grade. SOIC pin assignments: A1=1, A0=2, SDA=3, SCL=4, VS=5, GND=6, IN-=7, IN+=8. SOT23-8 assignments are different; never exchange footprints without remapping. A0/A1 to GND => 0x40, RTC DS3231M uses 0x68. Use local 100nF VS-to-GND and existing upper 4.7k SDA/SCL pullups only.

VS must come from upper SYS_3V3 through a separate connector contact. TI requires SCL <= VS+0.3V. With J11 removed for USB, lower FILTER_OUT may be off while upper I2C is high; lower-only VS is invalid. Analog battery inputs may be present while VS is off. VS range 3-5.5V, analog bus 0-26V.

12 contacts can remain by allocating 3 FILTER_OUT + 4 GND + BAT_RAW + MODE + SDA + SCL + SYS_3V3. Alternative preserve 4 FILTER_OUT with 3 GND. Preserve the manufacturer physical row/pin mapping under the 180-degree LOGIC inversion; logical same numbering on the old cable footprints does not imply pin mating.

## Shunt candidates / own calculations

Danomsk item215631: Viking LRP12FTDRR020, 20mOhm +/-1%, 2512, 3W, 50ppm/K. Fresh shop page: 30 pieces, 9.90R individual displayed price, 7.90R at10, sold in multiples10. Prefer this readily local documented metal shunt unless root chooses a 10mOhm part for lower drop. At4A: 80mV/0.32W; at1.25A:25mV/31.25mW; at0.714A:14.28mV/10.20mW. 10mOhm halves those numbers but doubles current equivalent ADC/offset error. 20mOhm ADC granularity is0.5mA versus1mA at10mOhm. Small standby microamp currents cannot be resolved reliably with either.

For a20mOhm shunt and +/-4A envelope, a firmware example is currentLSB=0.2mA, CAL=10240(0x2800), powerLSB=4mW, bus range16V, PGA +/-160mV. Current register extends to +/-6.5534A; the PGA allows +/-8A physically. Do not use +/-80mV full scale at4A with no margin. Kelvin takeoff at the inner resistor terminal edges, main current through wide copper, not the sense traces. Input footprints can support symmetric low resistance and differential capacitor; TI recommends10Ohm and0.1-1uF against fast transient interference, but qualify offset/settling at the chosen low shunt value. Keep sense routes away from TPS/CN switch nodes.

## MeshCore integration limitation

The local audited ProMicro profile and current upstream enable ENV_INCLUDE_INA219=1 at address0x40. EnvironmentSensorManager init calls INA219.begin() and direct current/power getters. Adafruit_INA2191.2.3 begin uses a fixed0.1Ohm calibration, so 20mOhm reports current/power5 times too low; 10mOhm reports10 times too low. Voltage remains valid. Do not claim correct stock telemetry with these low-drop shunts. Calibration is a necessary targeted firmware adaptation; preserve radio GPIO, existing BAT_ADC and I2C pins.

The default library leaves INA continuously converting. Typical VS current0.7mA, max1mA; powerdown6uA typical/15uA max. Prefer single triggered measurement then powerdown if energy saving matters, but do not claim that the stock binary already does this. Power telemetry sign must be validated for reverse battery current; derive signed P=Vbat*I from signed current when necessary. Existing accepted LTO limitations remain: no independent OVP and2Ohm balance resistors not upgraded.

## Primary sources

- TI datasheet RevG: https://www.ti.com/lit/ds/symlink/ina219.pdf (pin table p3, absolutes p4, electrical p5-6, supply sequencing p9, filter p11, registers p12+).
- MeshCore ProMicro: https://raw.githubusercontent.com/meshcore-dev/MeshCore/main/variants/promicro/platformio.ini
- MeshCore sensor manager: https://raw.githubusercontent.com/meshcore-dev/MeshCore/main/src/helpers/sensors/EnvironmentSensorManager.cpp
- Adafruit1.2.3 driver: https://raw.githubusercontent.com/adafruit/Adafruit_INA219/1.2.3/Adafruit_INA219.cpp
- LCSC INA219BIDR: https://www.lcsc.com/product-detail/C2155799.html (live fetch 5190 units, USD1.0866 qty1, qty10USD0.8899).
- Dan category with item215631: https://www.danomsk.ru/shop/6-rezistory/86-rezistory-postoyannye/501-rezistory-chip-1210-2512/
- Viking primary datasheet: https://www.viking.com.tw/Templates/att/LRP_Series.pdf?lng=en
- Viking exact MPN datasheet on LCSC: https://datasheet.lcsc.com/lcsc/2409271603_Viking-Tech-LRP12FTDRR020_C5120088.pdf
