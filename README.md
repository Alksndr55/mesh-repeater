# Mesh Repeater v1.25

Одноплатное ведущее исполнение 90×100 мм.

[Готовый архив KiCad](https://github.com/Alksndr55/mesh-repeater/releases/download/v1.25/Mesh_Repeater_v1.25_KiCad.zip) · [Страница выпуска](https://github.com/Alksndr55/mesh-repeater/releases/tag/v1.25)

## Открытие проекта

Полностью распакуйте архив перед открытием. Используйте KiCad 10 с официальными библиотеками; локальные модели и посадочные места включены.

- [MAIN](v1/design/Meshcore_NaIon/Meshcore_NaIon.kicad_pro)

Общая электрическая схема: [KiCad](shared/schematic/MeshRepeater.kicad_pro), [PDF](shared/output/pdf/MeshRepeater_schematic.pdf).

## Состав выпуска

Исправлены подводы дорожек и острые стыки, удалены лишние GND-дорожки поверх заливки, восстановлены реальные термобарьеры. Земляные vias расположены по сетке 5 мм; местные исключения записаны в `routing_review.json` каждой платы. Расстановка и критические RF/Kelvin-участки сохранены.

Watchdog **v1.00** включён в [v1/design/watchdog_reference](v1/design/watchdog_reference). Исходник и HEX совпадают с [канонической прошивкой](https://github.com/Alksndr55/watchdog/releases/tag/v1.00). Прошивка микросхемы и установка fuse выполняются отдельно.

- [Полный список изменений разводки](docs/ROUTING_RESULT_RU.md)
- [BOM](v1/bom/COMPONENT_BOM.csv) и [сборка](v1/docs/ASSEMBLY_RU.md)
- [Свежие проверки](v1/audit/current/checks.json)
- [Порядок выпуска](docs/WORKFLOW_RU.md), [аппаратные ограничения](docs/LIMITATIONS_RU.md)
- [Лицензия](v1/LICENSE.md)

ERC/DRC и соответствие общей схеме проверены для точных файлов выпуска. Проверка распакованного пакета выполнена независимо. Это инженерный прототип; CAD-проверки не являются испытанием платы.

Каталоги `v1/`, `shared/`, `docs/`, `tools/project/` составляют переносимый проект этого исполнения. Архив другого исполнения, исторические снимки и производственные пакеты в него не включены.

Designed by @Alksndritm.
