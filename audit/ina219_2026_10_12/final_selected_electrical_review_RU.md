# Final selected INA219 electrical seam — read-only review

Status: parent-selected0.1Ohm stock-calibration circuit. This supersedes the low-drop candidates in read_only_electrical_proposal_RU.md and the transient raw-CV assumption in selected_0p1R_electrical_review.json. No canonical CAD/models/BOM or firmware changed by this agent.

Topology: raw existing BAT at J8.1, J12.1, BAT_ADC sense interboard9, EN R15.1, LTO balancer R47.1 and TP1. New measurement shunt0.1Ohm separates raw BAT from BAT_SYS. Converter input, C4/C12/C13/C52/C53 and CN3722 charge output move to BAT_SYS; native copper should still feed through C53.1. Original charger R1=0.28Ohm and U1.BAT14 remain both referenced to BAT_SYS. R3.1 and C30.1 stay on BAT_SYS for CV stability and the existing normal-operation TPS5.5V ceiling. Raw battery charge voltage therefore equals the regulated BAT_SYS minus charging current times0.1Ohm; nominal charge droop71.4mV at714mA,78.85mV upper calculation. It approaches zero on taper. R15 sees raw battery so1.8/3.6V battery cutoff remains unchanged; TPS voltage under discharge is lower by I*0.1Ohm. Atproject1.25A designload,125mV drop/156mW resistor dissipation; INA stock ADC clips above3.2A so4A spikes are not valid measured values.

INA219AIDR SOIC8 pins:1A1GND,2A0GND,3SDA,4SCL,5VS fromupperSYS_3V3,6GND,7IN- rawBAT,8IN+ BAT_SYS. This polarity intentionally reports actual raw battery voltage in stock getBusVoltage_V, charging positive and discharge negative. Use the shared upperI2C4.7k pullups andlocal100nFVS bypass. Firmwareaddress0x40 differs fromRTC0x68. UpperSYS_3V3 return ensures SCL cannot pull an unpowered device high when J11 is removed forUSB. DirectlowerFILTER_OUT supply is incorrect inUSB mode. Twelvecontacts selected1FILTER_OUT,2GND,3FILTER_OUT,4GND,5FILTER_OUT,6GND,7SYS_3V3,8GND,9rawBAT,10SDA,11MODE,12SCL. Actual padphysicalmapping must account forLOGIC180degree inversion.

Balancing is tied directly toBAT/MID/GND to preserve true cell voltage and the accepted2Ohm circuit. Main shunt does not measure individual cell balancing bleed through the midpoint or direct raw taps; it measures external main pack current. Existing no-battery overvoltage andLMV4312Ohm accepted risks remain. No newnormaloperationLTO overvoltage is introduced withCV keptBAT_SYS. MovingCVto rawBAT while retainingR3=121k would produce5.5232V possibleBAT_SYS with the newshunt; that option was rejected by theparent. No R3 valuechange is required withCVsystem-side.

Firmware evidence, exact local paths and functions:
- audit/faketec_compatibility_20261009/upstream/MeshCore/variants/promicro/platformio.ini:25 enablesENV_INCLUDE_INA219 and:32 pinsAdafruit1.2.3.
- audit/faketec_compatibility_20261009/upstream/MeshCore/src/helpers/sensors/EnvironmentSensorManager.cpp:378 init_ina219 callsbegin(wire);382 query_ina219 readsVbusonly(:383),current_mA/1000(:384),power_mW/1000(:385). It does notsumVshunt.
- audit/faketec_compatibility_20261009/upstream/MeshCore/platformio.ini:27 pinsCayenneLPP1.6.1.
- Adafruit1.2.3 begin/init sets0.1Ohm calibration32V2A. getCurrent_raw():96-109 int16t, getCurrent_mA():154-157 float, so signedcurrent preserved.
- CayenneLPP1.6.1 getTypeSigned():532-563 includesCURRENT, addCurrent():671-673 acceptsfloat, addField():585-597 preservesnegative2scomplement. End-to-endnegativecurrent is supported. POWER isabsent fromsignedtypes: stockpowertelemetryhasnomagnitudedirection; inferdirectionfromcurrent. Do notclaim signedpower.
- INA continuousconversionstockcurrent0.7mAtyp/1mAmax, powerdown6uAtyp/15uAmax. Current firmware does notsleepINA by default. Do notclaimenergy-savingpolicyalreadyimplemented.

PrimaryURLs:
https://www.ti.com/lit/ds/symlink/ina219.pdf
https://raw.githubusercontent.com/meshcore-dev/MeshCore/main/src/helpers/sensors/EnvironmentSensorManager.cpp
https://raw.githubusercontent.com/meshcore-dev/MeshCore/main/variants/promicro/platformio.ini
https://raw.githubusercontent.com/adafruit/Adafruit_INA219/1.2.3/Adafruit_INA219.cpp
https://raw.githubusercontent.com/ElectronicCats/CayenneLPP/1.6.1/src/CayenneLPP.cpp
https://consonance-elec.com/static/upload/file/20231218/1702867485736775.pdf
