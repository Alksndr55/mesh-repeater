# Mesh Repeater 2.0

**Designed by @Alksndritm**

Репитер MeshCore / FakeTec ProMicro на Nice!Nano и HT-RA62, разделённый на две платы 90×60 мм со сплошным средним экраном. Нижняя плата содержит зарядку CN3722, TPS63802, LC-фильтр и опции COLD/LTO; верхняя — процессор, модем, RTC CR2032, GPS и аппаратный watchdog.

Версия 2.0 ведётся в отдельной ветке `mesh-repeater-2.0` от опубликованной [S4.16 / v1.0](https://github.com/Alksndr55/mesh-repeater/tree/v1.0), SHA `cf54f9970e716272d477afdb252b4e195d595cb6`. Ветка `main` сохраняет версию 1.0. Пакет производственного заказа 1.0 отложен по указанию владельца.

## Редактируемые проекты

Проверенная среда — KiCad 10.0.6. Открывайте `.kicad_pro`, сохраняя рядом локальные библиотеки и модели. `Alt+3` в редакторе платы открывает 3D.

| Проект | Схема | Плата |
|---|---|---|
| [POWER](design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pro) | [KiCad](design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_sch), [PDF](output/pdf/MeshRepeater2_Power_schematic.pdf) | [KiCad](design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb) |
| [LOGIC](design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pro) | [KiCad](design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_sch), [PDF](output/pdf/MeshRepeater2_Logic_schematic.pdf) | [KiCad](design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb) |
| [SHIELD](design/MeshRepeater2_Shield/MeshRepeater2_Shield.kicad_pro) | Механический экран | [KiCad](design/MeshRepeater2_Shield/MeshRepeater2_Shield.kicad_pcb) |

Рабочие платы имеют два слоя меди. Экран изготавливают с одним слоем F.Cu, направленным вниз; B.Cu пустой. KiCad сохраняет экран в двухслойном файловом контейнере. Физический состав отдельно задан в [README экрана](design/MeshRepeater2_Shield/README_RU.md).

## Сборка и обслуживание

LOGIC поворачивается на 180° вокруг X, компонентами к экрану. Стойки с телами 18 и 15 мм и металлические шайбы задают номинальные внутренние промежутки 18,5 и 16,0 мм. Высота между наружными поверхностями рабочих плат — 39,06 мм. Полный габарит текущей 3D-сборки с выступающей шпилькой — 98,00×70,01×45,56 мм; размерная цепь от гайки до головки винта — 44,98 мм. Внешний кабель требует дополнительного места, его длина уточняется по образцу. Рамка SH1 удалена по отдельной [проверке размеров](audit/v2_frame_mount_review.json).

J101/J201 — боковые 12-контактные Connfly DS1013-12RSIB-B-0. Между платами проходят четыре FILTER_OUT, шесть GND, BAT для измерения и MODE. SYS_3V3 остаётся на LOGIC: J11 соединяет её с FILTER_OUT и снимается перед USB. Кабель проверяют по всем двенадцати контактам как 1:1 с учётом переворота верхней платы. ISP J10 сохранён на исходном месте; программирование через него требует разборки.

- [Полная инструкция](docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md), [PDF](output/pdf/MeshRepeater2_assembly_manual_RU.pdf).
- [Межплатное соединение](design/interboard_cable.json) и [электрический контракт](design/v2_electrical_contract.json).
- [BOM компонентов и вариантов](bom/V2_COMPONENT_BOM.csv), [новые детали и крепёж из ДАН](bom/DAN_NEW_PARTS.csv).
- [Механическая спецификация](docs/mechanical_selection.json), [сборочные чертежи и модели](docs/mechanics/).
- [Ограничения и проверки на образце](docs/V2_LIMITATIONS_RU.md).
- [Просмотр плат и сборки](output/V2_OVERVIEW_RU.html), [восстановление экспортов STEP](docs/STEP_TRANSPORT_RU.md).

Варианты Na-ion 1S с COLD, Na-ion без COLD и LTO 2S сохраняют номиналы S4.16. Функциональные связи, выводы MCU и прошивка MeshCore / FakeTec не меняются; добавлены межплатные соединители и боковое механическое исполнение органов управления.

Это инженерный прототип. CAD-проверки схемы, трассировки и геометрии относятся к сохранённым файлам с хешами. Испытания EMI, устойчивости преобразователя с LC, допустимости режимов ячеек, питания от конкретного Nice!Nano-клона и реального сопряжения разъёмов/крепежа остаются необходимыми. Упрощённые модели модулей и некоторых деталей не подтверждают их точную механическую посадку.

`baseline/S4_16/` — замороженный оригинал. Унаследованные `design/Meshcore_NaIon`, S4.* PDF и отчёты относятся к версии 1.0 и доступны также по тегу `v1.0`. Начальная точка входа для новых файлов — [START_HERE_RU.md](START_HERE_RU.md).
