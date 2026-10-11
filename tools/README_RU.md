# Сценарии проекта 2.0

Историческое сравнение `check_v2_logic_star_fix.py` использует локальный снимок
`audit/routing_logic_star/before_star.kicad_pcb`, который не публикуется.
Его результаты и контрольные суммы сохранены в `audit/v2_logic_star_fix.json`.
Итоговые проверки `verify_v2_native_boards.py` и `audit_v2_routing_engineering.py`
работают по опубликованным окончательным проектам без этого снимка.

Итоговые редактируемые файлы находятся в design/MeshRepeater2_Power, design/MeshRepeater2_Logic и design/MeshRepeater2_Shield. Это актуальная версия CAD. Сценарии построения и локальных правок в cad/ использовались на последовательных промежуточных снимках; они не являются одной идемпотентной командой пересборки окончательной трассировки. Повторный запуск build_v2_boards.py или select_v2_mechanics.py на окончательных файлах может заменить проверенную разводку исходной компоновкой. Для экспериментов используйте отдельную копию проекта.

Повторные проверки без изменения CAD:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' tools/verify_v2_native_boards.py --stage final --out audit/v2_native_boards_final.json
& 'C:/Program Files/KiCad/10.0/bin/python.exe' tools/audit_v2_routing_engineering.py
& 'C:/Program Files/KiCad/10.0/bin/kicad-cli.exe' pcb drc --format json --severity-all --schematic-parity -o audit/recheck_power_drc.json design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb
& 'C:/Program Files/KiCad/10.0/bin/kicad-cli.exe' pcb drc --format json --severity-all --schematic-parity -o audit/recheck_logic_drc.json design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb
```

export_v2_board.py экспортирует сохранённую плату в SVG/STEP и собственный хеш-манифест. build_v2_assembly.py читает эти STEP и проверяет их соответствие текущим PCB до формирования сборочных моделей. Визуальные модели некоторых купленных модулей приблизительны; результаты CAD не заменяют обмер и испытания образца.

Часть штатных 3D-моделей использует стандартные библиотеки KiCad 10 и переменную KICAD10_3DMODEL_DIR. Локальные нестандартные модели входят в каждый проект. При открытии установите стандартные библиотеки KiCad соответствующей версии.
