# Независимый аудит механики Mesh Repeater 2.0 — 12 октября 2026

HEAD: `547740fee937f891568f18485c7a6a3733c234c9`. CAD, библиотеки и настройки не изменялись. Независимо читались native KiCad, raw STEP и FCStd; старый geometry PASS не использован как самостоятельное доказательство.

## Новые замечания

### M-01 — P2: BOM не содержит ответных кабельных частей новых угловых J3/J5

Один DS1022-1x40RUF11-B разрезается на J11/J3/J5, но это только платные вилки. Для J11 шунт отдельно указан, для J3 и J5 ни 4-контактные кабельные корпуса, ни гнездовые контакты/готовые кабели не перечислены. Поэтому по спискам 2.0 нельзя собрать и проверить все выбранные внешние соединения; конечный габарит и доступ с ответной частью также не определены.

Доказательство: bom/DAN_NEW_PARTS.csv:5; bom/V2_COMPONENT_BOM.csv:134; bom/V2_COMPONENT_BOM.csv:136; docs/Mesh_repeater_v2_Codex_prompt_RU.txt:185. Координаты native: `{'J3': [86, 12, 0], 'J5': [2.5, 18.12, 180]}`. Уверенность 98%.

Предлагаемая последующая правка: При последующей правке добавить проверенные кабельные гнёзда/контакты либо конкретные готовые 1x4 кабели с количеством, применимостью ко всем трём вариантам, размером и схемой нумерации, затем проверить вставку и снятие в собранных этажах.

### M-02 — P3: Упрощённая STEP кнопки не покрывает полный наружный размер скобы

Габарит локальной STEP по X составляет -3.83..3.83 =7.66мм. TE drawing задаёт 8.41мм для внешней скобы. Недостают 0.375мм с каждого края. Courtyard ±4.455мм верно учитывает настоящую ширину скобы, поэтому подтверждённого пересечения или ошибки отверстий здесь нет; ограничение относится к полноте визуальной/3D проверки.

Доказательство: tools/cad/build_v2_mechanical_library.py:294; tools/cad/build_v2_mechanical_library.py:50; docs/mechanical_sources/SW1_TE.pdf, page1, front-view bracket width8.41mm; audit/independent_2026_10_12/mechanics.geometry.json, models.SW_TE_1825027_2_Side.step. Координаты native: `{'SW1': [29, 58.2, 180], 'SW2': [41, 58.2, 180]}`. Уверенность 99%.

Предлагаемая последующая правка: При последующей правке использовать точную TE STEP либо консервативно расширить оболочку скобы до ±4.205мм, затем повторить геометрическую проверку. Сейчас не ссылаться на эту STEP как на полный реальный наружный контур скобы.

## Проверка требований

| Требование | Статус и доказательство |
|---|---|
| 90x60 POWER/LOGIC/SHIELD | PASS_CAD — Native PCB edges nominal 0..90 /0..60; GetBoardEdgesBoundingBox includes 0.025mm stroke each side. Raw STEP core solids have exact90x60 footprint. |
| 4xM3 alignment and GND contact construction | PASS_CAD_SAMPLE_PENDING — Four centres (3.5,3.5),(86.5,3.5),(3.5,56.5),(86.5,56.5), drills3.2. POWER/LOGIC plated pads OD6 netGND exposed both sides; SHIELD F.Mask circlesOD6, foil has clearance about0.3 around NPTH. DIN433 metal washersOD6/ID3.2 provide annular contact; lower GND return also exists via lower washer/nut/stud. No claim of measured contact resistance. |
| single sided continuous shield | PASS_CAD — Native F.Cu0.035/core1.475/B.Cu0/B.Mask0; actual shield contains one connected foil solid, thickness0.035 and no letter cuts; F side faces down afterX180. |
| stack dimensions/no overlap | PASS_CAD_APPROXIMATE_MODELS — Independent raw STEP + FCStd measurement: gapsPOWER5.960mm/LOGIC5.270mm; both complete vertical envelopes are disjoint from shield, hence no board-to-board intersection. Independent component-to-arbitrary-hex-cylinder test min1.4045735mm at north-east IDC; other corners proven>=2mm. |
| LOGIC orientation and J10 preservation | PASS_CAD — NativeLOGIC F components, assemblyX180, exterior B silk. ActualJ10(35.7,31.3)0deg. Service after disassembly follows explicit user clarification. |
| SH1 decision | PASS_DOCUMENTED_CHANGE_EMI_PENDING — SH1 absent from actual POWER; docsV2_ASSEMBLY_INSTRUCTIONS_RU.md:26 and V2_LIMITATIONS_RU.md:23 explicitly document frame/lid removal. Middle horizontal foil remains. No closed conductive cage or vertical walls exist. |
| side access USB/SMA/GPS/I2C/UART/SW/J11 | PASS_PLACEMENT_PHYSICAL_ACCESS_PENDING — Actual native positions and STEP directions agree with chosen outer edges. USB/SMA/mating plugs/clones use approximate or absent actual models; fitted plug envelope/tool access cannot be marked proven. |
| LED D3/D4 edge and LOGIC operator projection | PASS_CAD_OPTICAL_PENDING — ActualPOWER D3(51,2.2),D4(56,2.2) are ordinaryLED0805 at common north edge; their circuits remainPOWER. NativeLOGIC B operator label at(54,56) projects physical(54,4) afterX180, at same north edge; no upperLED introduced. Actual brightness/view angle not tested. |
| marking/readability/minimum0.8 | PASS_CAD — Visible F/B silk min0.8mm on functionalboards and >=0.88mm screen; inspected actual exportfront/back/operator-top/SHIELDassemblytop. LOGICB text mirrored+180 yields readable final top. POWERB includes intentionally displaced labelled spatial insets, not every individual body projection; original strict external operator projection requirement concernsLOGIC. |
| 12wire1to1 | PASS_NATIVE_PINMAP_ASSEMBLED_CABLE_PENDING — Both actualJ101/J201 pin map: odd1/3/5/7FILTER_OUT,evenGND,9BAT,11MODE; SYS_3V3 absent. Physicalpin1 X sides oppose afterLOGICX180. Prescribed half-twist/customwire1:1 remains mandatory continuity check; keys alone do not prove wiring. |
| fastener stack/thread depth | PASS_NOMINAL_CHAIN_SAMPLE_PENDING — 18/15mm metalstandoffs, five0.5mm washers/corner, fourM3nut/fourM3x6. Nominal upperstud/screw engagement3.48mm, loweravailablethread2.98mm. RUICHI5mm stud/~6mm depth approximate; upperConnfly usefulfemalethreaddepth absent. This is explicitly pendingincomingqualification. |
| all three variants and newpart BOM applicability | PARTIAL — NaIonCOLD/NaIonNoCOLD/LTO columns present; J12native4pin addsNC4 and matchingKLS4polehousing+3contacts. J7/J8mates, IDCbothhalves, J11shunt and fasteners listed. J3/J5mates absent(M-01). OriginalprecisionMPN gaps remaindocumented and must not be upgraded to procurementPASS. |

## Физически не проверено

- Actual installed NiceNano clone/socket height, USB plug shell and full insertion/removal; retained clone charger modification and USB LDO current capability.
- IDC male/female mating depth, assembled female+strain-relief axial dimension, 12-wire continuity1:1 after half-twist, cable length120mm and bendradius/slack. No exact female/cable model inassembly.
- J11 DS1027-2BBN1 on right-angle DS1022: actual insertion depth/contact and removal/reinstallation with fingers or pincers. Unused localDS1027 file describes previous vertical placement; installed horizontal shunt absent fromassemblymodel.
- J3/J5 cable mates after parts are selected; GPS realHeltec cable numbering, mate and clearance; SMA antenna plug/cable; USB cable with buttons.
- Usable female thread depths, chamfers/first full thread and tolerance chain; upperengagement>=3mm, lowernutfullengagement and no bottoming.
- Four GND contacts after torque, mask/finish/washer tolerances, standoff metallic continuity and resistance across screen; keep functionalpowerreturn through cable.
- D3/D4 side optical visibility/brightness after actualIDC cable routed nearby; button finger pressure and mechanism on assembly.
- Temperature/EMI with removed SH1: middle plate is not closedcage; heat from CN3722/TPS63802/LTO ballast and localNTC battery-temperature error.
- Cable specification-20..+70C; operation below-20C requires separatelyqualified cable; no new procurement check was inferred from historical11Octoberstock.
- Electricalbench from inherited electronics: LTO/no-battery transient, cellprotection/LMV431A ballast, LC effectivecapacitance/loadstep, batteryADCgrounddrop, GPS start/backpower, watchdogtiming/recovery, radio/MCUrail sag. Other auditors own electrical detail.

Наличие из BOM от 11 октября 2026 года трактуется как историческая проверка. Заказ/резервирование не выполнялись. Прямые источники и контрольные суммы сохранены в mechanics.json; независимые размеры — в mechanics.native.json, mechanics.geometry.json и mechanics.fit.json.

Проекция среднего экрана с читаемым верхом проверена по output/SHIELD/MeshRepeater2_Shield_assembly_top.png. Не требуется оценивать перевёрнутый native B-preview как дефект ориентации окончательной сборки.
