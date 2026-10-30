# Mesh Repeater v1.25

Designed by @Alksndritm. Текущее исполнение общего проекта.
Ведущая разводка.
Выпуск от 30.10.2026: [v1.25 на GitHub](https://github.com/Alksndr55/mesh-repeater/releases/tag/v1.25).
Предыдущая публикация — [v1.22](https://github.com/Alksndr55/mesh-repeater/releases/tag/v1.22)
(прежнее обозначение S4.22). Следующий номер — v1.26.

[MAIN](design/Meshcore_NaIon/Meshcore_NaIon.kicad_pro)

[Общая схема](../shared/schematic/MeshRepeater.kicad_pro) ·
[BOM](bom/COMPONENT_BOM.csv) · [Сборка](docs/ASSEMBLY_RU.md) ·
[Порядок выпуска](../docs/WORKFLOW_RU.md) · [Лицензия](LICENSE.md).

Текущие экспорты находятся в output/current, проверки — в audit/current.
Версия и состав задаются корневым project.json. CAD остаётся редактируемым;
общий процесс выпуска сохраняет геометрию и проверяет соответствие общей схеме.
Опубликованные исторические теги сохраняют свои прежние имена.

Дорожки и GND-переходы приведены к [общим правилам](../docs/ROUTING_RULES_RU.md).
[Результат и исключения сетки](../docs/ROUTING_RESULT_RU.md).
Включён [watchdog v1.00](design/watchdog_reference/INTEGRATION_RU.txt)
с каноническими исходником и HEX; LFUSE=0x73, HFUSE=0xFB, ISP 100 мкс.
Локальный архив этого выпуска создаётся в `../releases/v1.25/`.
