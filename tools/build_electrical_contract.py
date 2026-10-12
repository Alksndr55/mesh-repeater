"""Read S4.16 without modifying it; write only the 2.0 electrical contract.

This is a partition proposal and baseline proof, not a final 2.0 ERC/DRC result.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent.parent if ROOT.parent.name == "projects" else ROOT.parent
SOURCE = ROOT / "baseline" / "S4_16"
NETLIST = ROOT / "audit" / "source_s4_16" / "native_netlist.xml"
EXPECTED_PCB = "742ae27bb1d13893f6dc368e5c67f5c41b35a3e6765331fc7e9871297d23dec6"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    assert ROOT.name in {"Mesh_Repeater_2_0", "v2"}, ROOT
    assert sha(SOURCE / "Meshcore_NaIon.kicad_pcb") == EXPECTED_PCB
    model = json.loads((SOURCE / "model.json").read_text(encoding="utf-8"))
    manifest = json.loads((SOURCE / "schematic_manifest.json").read_text(encoding="utf-8"))
    variants_path = SOURCE / "assembly_variants_S4_16.csv"
    variants = list(csv.DictReader(variants_path.open(encoding="utf-8-sig", newline="")))
    variant_by_ref = {r["Reference"]: r for r in variants}
    parts = model["parts"]
    refs = {p["ref"] for p in parts}
    assert len(parts) == len(refs) == 167
    assert set(variant_by_ref) == refs
    xml = ET.parse(NETLIST).getroot()
    xml_parts = {c.attrib["ref"]: c for c in xml.find("components")}
    assert set(xml_parts) == refs

    power_groups = {"charger", "converter", "filter", "lto_balancer", "cold_charge"}
    power_extra = {"C8", "R10", "D3", "R11", "D4", "J7", "J8", "TP1", "TP3", "TP6", "H1", "H2", "H3", "H4", "SH1"}
    logic_exception = {"J11"}
    board_by_ref = {
        p["ref"]: "POWER" if (p.get("group") in power_groups or p["ref"] in power_extra) and p["ref"] not in logic_exception else "LOGIC"
        for p in parts
    }
    assert board_by_ref["R21"] == "LOGIC"
    assert board_by_ref["R17"] == "POWER"
    assert all(board_by_ref[r] == "LOGIC" for r in ["J11", "R27", "R28", "C25", "FB1", "C23", "C24", "M1", "M2", "BT1", "SW1", "SW2"])
    assert all(board_by_ref[r] == "POWER" for r in ["D3", "D4", "J7", "J8", "J12"])

    model_nodes = defaultdict(set)
    model_pins = {}
    for p in parts:
        for pin, net in p.get("nets", {}).items():
            model_pins[(p["ref"], str(pin))] = net
            if net is not None:
                model_nodes[net].add((p["ref"], str(pin)))
    xml_nodes = {}
    pin_to_native = {}
    nc_nodes = {}
    for net in xml.find("nets"):
        name = net.attrib["name"]
        nodes = {(n.attrib["ref"], n.attrib["pin"]) for n in net.findall("node")}
        (nc_nodes if name.startswith("unconnected-") else xml_nodes)[name] = nodes
        for node in nodes:
            assert node not in pin_to_native
            pin_to_native[node] = name
    model_to_native = {}
    for name, nodes in model_nodes.items():
        matches = [native for native, endpoints in xml_nodes.items() if endpoints == nodes]
        assert len(matches) == 1, (name, matches)
        model_to_native[name] = matches[0]
    assert len(model_to_native) == len(xml_nodes) == 86
    assert {node for endpoints in nc_nodes.values() for node in endpoints} == {node for node, net in model_pins.items() if net is None}
    for ref, element in xml_parts.items():
        p = next(p for p in parts if p["ref"] == ref)
        assert element.findtext("value") == p["value"], (ref, element.findtext("value"), p["value"])
        assert variant_by_ref[ref]["Value_NaIon"] == p["value"], ref

    cross = []
    for name, nodes in model_nodes.items():
        boards = {board_by_ref[ref] for ref, _ in nodes}
        if boards == {"POWER", "LOGIC"}:
            cross.append(name)
    assert sorted(cross) == ["BAT", "FILTER_OUT", "GND", "MODE"], cross

    reasoning = {
        "J11": "Верхняя плата: сохраняет единственный штатный переход FILTER_OUT → SYS_3V3; съёмный шунт доступен сбоку.",
        "R21": "Верхняя плата: существующий 1 кОм последовательно у источника RADIO_TXEN, до кабеля MODE; номинал не меняется.",
        "R17": "Нижняя плата: существующий pulldown MODE у U2.2 сохраняет Power Save при отсоединённой верхней плате.",
        "R27": "Верхняя плата у MCU: BAT приходит отдельным проводом непосредственно от аккумуляторного разъёма; высокоомный BAT_ADC остаётся локальным.",
        "R28": "Верхняя плата у MCU: нижнее плечо 2,2 МОм подключается к локальной GND у C25 и M1.",
        "C25": "Верхняя плата у M1.8: RC-фильтр ADC остаётся локальным; номинал 100 нФ и отношение 1:2 сохраняются.",
        "FB1": "Верхняя плата: отдельная локальная ветвь питания модема после J11.2.",
        "C23": "Верхняя плата: локальный накопительный конденсатор RADIO_3V3 непосредственно у M2.3.",
        "C24": "Верхняя плата: локальная ВЧ-развязка непосредственно у M2.3 и его GND.",
        "TP6": "Нижняя плата: сервисная земля силовой платы.",
        "TP7": "Верхняя плата: сервисная земля логической платы.",
        "H1": "Нижняя плата: исходная механическая позиция. Дополнительные отверстия верхней платы и экрана вводятся отдельно с теми же XY.",
        "H2": "Нижняя плата: исходная механическая позиция. Дополнительные отверстия верхней платы и экрана вводятся отдельно с теми же XY.",
        "H3": "Нижняя плата: исходная механическая позиция. Дополнительные отверстия верхней платы и экрана вводятся отдельно с теми же XY.",
        "H4": "Нижняя плата: исходная механическая позиция. Дополнительные отверстия верхней платы и экрана вводятся отдельно с теми же XY.",
        "SH1": "Рамка исходного экрана закреплена за силовой платой; решение сохранить/снять зависит от механики. Крышка не устанавливается. Это не решение автоматически удалить рамку.",
    }
    for ref in ["D3", "D4", "R10", "R11"]:
        reasoning[ref] = "Нижняя плата: цепь индикации зарядки остаётся целиком у CN3722; через межплатное соединение не проходит."
    sheet_by_ref = {ref: sheet["name"] for sheet in manifest["sheets"] for ref in sheet["refs"]}
    contract_parts = []
    rows = []
    for p in parts:
        ref = p["ref"]
        row = variant_by_ref[ref]
        reason = reasoning.get(ref, "Основной силовой/зарядный/фильтрующий узел." if board_by_ref[ref] == "POWER" else "Локальный потребитель, интерфейс или связанная с ним цепь на логической плате.")
        exact_pins = {pin: {"logical_net": net, "native_net": pin_to_native.get((ref, pin)), "no_connect": net is None} for pin, net in p.get("nets", {}).items()}
        contract_parts.append({"reference": ref, "board": board_by_ref[ref], "original_sheet": sheet_by_ref.get(ref), "reason_ru": reason, "mechanical_status": "decision_pending" if ref == "SH1" else "original_pinout_and_electrical_function_preserved", "original_model_part": p, "exact_netpins": exact_pins, "assembly_variant_row": row})
        rows.append({"Reference": ref, "Board": board_by_ref[ref], "Original_Sheet": sheet_by_ref.get(ref, ""), "Original_Group": p.get("group", ""), "Original_Value": p["value"], "Original_Footprint": p["footprint"], "Pins_JSON": json.dumps(exact_pins, ensure_ascii=False, separators=(",", ":")), **{k: row[k] for k in row if k not in {"Reference", "Footprint", "Vendor_URL"}}, "Reason_RU": reason})

    interface_details = {
        "FILTER_OUT": {"source": "POWER", "receiver": "LOGIC", "direction": "POWER_TO_LOGIC", "purpose_ru": "Готовые 3,3 В после обоих LC-каскадов, только к J11.1; SYS_3V3 находится после J11.2 и отсутствует в кабеле.", "continuous_design_current_A": 0.5, "contact_requirement_ru": "Каждый отдельный питающий контакт должен выдерживать весь расчётный ток 0,5 А; дублирование не заменяет паспортный ток и проверку распределения токов.", "voltage_range_V": [0, 3.3]},
        "GND": {"source": "POWER", "receiver": "LOGIC", "direction": "BIDIRECTIONAL_REFERENCE_RETURN", "purpose_ru": "Полноценный рабочий возврат питания и сигнальная земля; не требует проводимости стоек или экрана.", "continuous_design_current_A": 0.5, "contact_requirement_ru": "Каждый отдельный контакт GND должен выдерживать 0,5 А. Контакты GND возле BAT и MODE уменьшают площадь сигнальных петель.", "voltage_range_V": [0, 0]},
        "BAT": {"source": "POWER", "receiver": "LOGIC", "direction": "POWER_TO_LOGIC_SENSE_ONLY", "purpose_ru": "Отдельный BAT sense от J8.1 либо J12.1 к R27.1; верхняя плата не питается этой сетью. R27/R28/C25 и BAT_ADC у MCU.", "continuous_design_current_A": 1.25e-6, "contact_requirement_ru": "Ток делителя при 5,5 В — 1,25 мкА; учитывать краткий заряд C25 и отсутствие перестановки с FILTER_OUT. Сеть остаётся BAT без нового электрического узла.", "voltage_range_V": [0, 5.5]},
        "MODE": {"source": "LOGIC", "receiver": "POWER", "direction": "LOGIC_TO_POWER", "purpose_ru": "Существующий сигнал TXEN модема через R21=1 кОм управляет U2.2 MODE; R17=100 кОм остаётся у U2. Watchdog по-прежнему получает RADIO_TXEN через R38 на верхней плате.", "continuous_design_current_A": 3.3e-5, "contact_requirement_ru": "Логическая сеть 3,3 В, последовательный R21 до кабеля; сопровождать GND. R17 обеспечивает LOW при разъединении.", "voltage_range_V": [0, 3.3]},
    }
    contact_plan = [(1, "FILTER_OUT"), (2, "GND"), (3, "FILTER_OUT"), (4, "GND"), (5, "FILTER_OUT"), (6, "GND"), (7, "BAT"), (8, "GND"), (9, "MODE"), (10, "GND")]
    interboard = []
    for pin, name in contact_plan:
        d = interface_details[name]
        interboard.append({"Net": name, "Native_Net_S4_16": model_to_native[name], "Source_Board": d["source"], "Source_Connector": "J14" if d["source"] == "POWER" else "J15", "Source_Contact": pin, "Mate_Connector": "J15" if d["source"] == "POWER" else "J14", "Mate_Contact": pin, "Receiver_Board": d["receiver"], "Direction": d["direction"], "Design_Current_A": d["continuous_design_current_A"], "Purpose_RU": d["purpose_ru"], "Status": "PROPOSAL_CONTACT_GEOMETRY_PENDING", "Original_POWER_Pins": ";".join(f"{ref}.{p}" for ref, p in sorted(model_nodes[name]) if board_by_ref[ref] == "POWER"), "Original_LOGIC_Pins": ";".join(f"{ref}.{p}" for ref, p in sorted(model_nodes[name]) if board_by_ref[ref] == "LOGIC")})
    nets = [{"logical_net": name, "native_net": model_to_native[name], "cross_board": name in cross, "nodes": [{"reference": r, "pin": pin, "board": board_by_ref[r]} for r, pin in sorted(nodes)]} for name, nodes in sorted(model_nodes.items())]
    source_inputs = {"pcb": SOURCE / "Meshcore_NaIon.kicad_pcb", "model": SOURCE / "model.json", "schematic_manifest": SOURCE / "schematic_manifest.json", "variants": variants_path, "native_netlist": NETLIST}
    sources = {k: {"workspace_relative_path": str(p.relative_to(WORKSPACE)).replace("\\", "/"), "sha256": sha(p)} for k, p in source_inputs.items()}
    sources["schematics"] = [{"file": p.name, "sha256": sha(p)} for p in sorted(SOURCE.glob("*.kicad_sch"))]
    old_metadata_conflicts = [
        {"field": "assembly_variants.Na-ion.R3_ohm/R4_ohm", "stale_model": [6340, 10000], "authoritative_S4_16_CSV_and_native": [61900, 100000]},
        {"field": "assembly_variants.LTO_2S.R3_ohm/R4_ohm", "stale_model": [13000, 10500], "authoritative_S4_16_CSV": [121000, 100000]},
        {"field": "status", "stale_model": model.get("status"), "authoritative_revision": "S4.16"},
    ]
    contract = {
        "project": "Mesh Repeater 2.0", "contract_revision": "V2_ELECTRICAL_PARTITION_01", "date": "2026-10-11", "stage": "PARTITION_AND_INTERFACE_PROPOSAL_NOT_FINAL_CAD", "source_product": "Mesh Repeater 1.0", "source_CAD_revision": "S4.16", "published_source_commit": "cf54f9970e716272d477afdb252b4e195d595cb6", "source_inputs": sources,
        "source_precedence": ["native S4.16 connected-pin graph and default values", "assembly_variants_S4_16.csv for each assembly variant", "model.parts matching native source", "model summary metadata only when consistent"],
        "board_components_count": dict(Counter(board_by_ref.values())), "component_count_original": 167, "parts": contract_parts, "nets": nets, "no_connect_pins": [{"reference": r, "pin": pin, "native_net": name} for name, endpoints in nc_nodes.items() for r, pin in sorted(endpoints)],
        "cross_board_nets": sorted(cross), "interface_net_requirements": interface_details, "interboard_contact_proposal": interboard,
        "allocated_assembly_variants": ["Na-ion cold", "Na-ion no cold", "LTO 2S"], "assembly_variant_rows_unchanged": True,
        "mechanical_changes_authorized": ["J7/J8/J12 side entry, electrical pin order retained", "J3/J5/J10 side access, electrical pin order retained", "J4 horizontal PicoBlade retained", "J11 right-angle removable shunt, electrical nets/pin numbers retained", "SW1/SW2 side actuation; electrical contact pair retained", "additional mounting contacts/holes and interboard connectors", "SH1 frame decision pending; original lid removed"],
        "electrical_invariants": {
            "original_ref_mapping": "identity; every original reference is allocated exactly once to one functional PCB", "J11": {"board": "LOGIC", "pins": {"1": "FILTER_OUT", "2": "SYS_3V3"}, "cable_has_no_SYS_3V3": True, "operation": "Battery/solar: fitted. Remove before USB; refit after USB disconnection. Neither direct copper nor a second connector may bridge these networks."},
            "battery_ADC": {"parts_board": "LOGIC", "parts": ["R27", "R28", "C25"], "BAT_pickoff": "J8.1 / J12.1 on POWER, separate trace to interboard BAT contact", "high_impedance_ADC_trace": "Only on LOGIC between R27/R28/C25 and M1.8", "divider_ratio": 2, "tau_s": 0.11},
            "TPS_MODE": {"source": ["M2.5", "M2.7"], "source_net": "RADIO_TXEN", "source_series": "R21=1k on LOGIC", "cross_net": "MODE", "lower_input": "U2.2", "lower_pulldown": "R17=100k", "watchdog_input_path": "RADIO_TXEN → R38=1k → WDT_INPUT/U6.2, entirely on LOGIC"},
            "radio_local_supply": {"board": "LOGIC", "path": "J11.2/SYS_3V3 → FB1 → RADIO_3V3/M2.3", "local_bypass": ["C23", "C24"], "note": "Common GND remains continuous; FB1 suppresses HF coupling but does not guarantee no TX load-step sag."},
            "charge_LED_networks": {"board": "POWER", "parts": ["D3", "D4", "R10", "R11"], "cross_board_networks": [], "operator_top_text_only": True},
            "firmware_GPIO": model["pinmap_s4_4"], "GPS": model["gps_s4_7"], "shield_return": "All power/signal return contacts are in the cable. Metallic spacers and shield only improve shielding; electrical functionality must remain with insulated spacers."
        },
        "baseline_metadata_conflicts": old_metadata_conflicts, "inherited_open_items": model["open_items"], "final_verification_pending": ["actual 2.0 board schematics equivalent to this partition after collapsing connector links", "variant fit/value comparison against full S4.16 CSV", "J11 removed/USB whole-device bench check", "ERC/DRC and schematic/PCB parity of both saved boards", "cable pin number and mating orientation after mechanical part selection", "PCB/cable transient drop and radio load-step measurements", "screen current independent cable continuity", "mechanical, clearance, assembly and access verification"],
        "checks": {"source_pcb_hash_matches_accepted": True, "167_refs_model_XML_CSV_identical": True, "default_native_values_match_model_and_CSV": True, "86_connected_graphs_exactly_match_model_and_native_XML": True, "16_no_connect_pins_match": True, "every_original_component_allocated_once": True, "crossnets_exactly_FILTER_OUT_GND_BAT_MODE": True, "SYS_3V3_not_interboard": True, "charge_LED_networks_not_interboard": True, "final_2_0_CAD_verified": False},
    }
    write_json(ROOT / "design" / "v2_electrical_contract.json", contract)
    for filename, csvrows in [("component_partition.csv", rows), ("interboard_nets_proposal.csv", interboard)]:
        path = ROOT / "docs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(csvrows[0]))
            writer.writeheader()
            writer.writerows(csvrows)
    print(json.dumps({"parts": len(parts), "boards": contract["board_components_count"], "crossnets": sorted(cross), "connected_nets": len(nets), "no_connect_pins": len(contract["no_connect_pins"]), "source_verified": True, "outputs": ["design/v2_electrical_contract.json", "docs/component_partition.csv", "docs/interboard_nets_proposal.csv"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
