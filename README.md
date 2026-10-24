# Mesh Repeater v1.22

Designed by @Alksndritm. Одноплатное исполнение 90×100 мм, ведущая разводка общего проекта. Общая схема содержит 150 функциональных позиций; текущая BOM — 154 позиции и три варианта сборки. Прежнее обозначение этой редакции — S4.22.

[Скачать готовый KiCad ZIP](https://github.com/Alksndr55/mesh-repeater/releases/download/v1.22/Mesh_Repeater_v1.22_KiCad.zip) · [SHA256](https://github.com/Alksndr55/mesh-repeater/releases/download/v1.22/SHA256SUMS.txt) · [Описание выпуска](https://github.com/Alksndr55/mesh-repeater/releases/tag/v1.22).

- [Открыть плату MAIN в KiCad](v1/design/Meshcore_NaIon/Meshcore_NaIon.kicad_pro).
- [Общая электрическая схема](shared/schematic/MeshRepeater.kicad_pro), [PDF](shared/output/pdf/MeshRepeater_schematic.pdf), [физические профили](shared/variants.json).
- [BOM](v1/bom/COMPONENT_BOM.csv), [сборка v1](v1/docs/ASSEMBLY_RU.md), [общая сборка](docs/ASSEMBLY_COMMON_RU.md).
- [Свежие проверки CAD](v1/audit/current/checks.json), [проверка BOM](v1/audit/current/bom.json), [состав выпуска](RELEASE_MANIFEST.json).
- [Единый процесс выпуска](docs/WORKFLOW_RU.md), [лицензия](v1/LICENSE.md).

Для редактирования нужен KiCad 10 со стандартными библиотеками. Локальные библиотеки, модели, watchdog и текущие проверяющие команды входят в проект. Производственный экспорт выполняется отдельно.

Инженерный прототип. Нулевые ERC/DRC не заменяют испытаний собранной платы. Перед USB снять J11; доработка Nice!Nano и принятые ограничения LTO сохраняются. [Полный перечень ограничений](docs/LIMITATIONS_RU.md).
