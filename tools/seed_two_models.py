"""Seed the two V2 models from frozen S4.16; never overwrite developed models.

The initial positions and new connector templates are a layout starting point.
They are not a checked mechanical design, routed PCB, or stock availability claim.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "baseline" / "S4_16"
CONTRACT = ROOT / "design" / "v2_electrical_contract.json"
KICAD_FP = Path("C:/Program Files/KiCad/10.0/share/kicad/footprints")
PCB_SHA = "742ae27bb1d13893f6dc368e5c67f5c41b35a3e6765331fc7e9871297d23dec6"
HOLES = [(3.5, 3.5), (86.5, 3.5), (3.5, 56.5), (86.5, 56.5)]
CONTACT_NETS = {str(i): "GND" if i % 2 == 0 else "FILTER_OUT" if i < 9 else "BAT" if i == 9 else "MODE" for i in range(1, 13)}


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_part(ref, kind, value, nets, footprint, x, y, rotation, group, note):
    return dict(ref=ref, kind=kind, value=value, nets=nets, footprint=footprint,
                x=x, y=y, rotation=rotation, group=group, note=note,
                mpn="PENDING_MECHANICAL_SELECTION", lcsc="", dnp=False,
                fit_naion=True, fit_lto2s=True, fit_naion_no_cold=True,
                assembly_default_dnp=False,
                assembly="All variants: FIT",
                schematic_uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, "MeshRepeater2:" + ref)))


def copy_if_absent(src, dst):
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for entry in src.iterdir():
            copy_if_absent(entry, dst / entry.name)
    elif not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main():
    assert ROOT.name in {"Mesh_Repeater_2_0", "v2"}
    assert hashlib.sha256((BASE / "Meshcore_NaIon.kicad_pcb").read_bytes()).hexdigest() == PCB_SHA
    baseline = json.loads((BASE / "model.json").read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    partition = {p["reference"]: p for p in contract["parts"]}
    destinations = {board: ROOT / "design" / ("MeshRepeater2_Power" if board == "POWER" else "MeshRepeater2_Logic") for board in ["POWER", "LOGIC"]}
    for dest in destinations.values():
        if (dest / "model.json").exists():
            raise RuntimeError(f"Refusing to overwrite a developed model: {dest / 'model.json'}")
    initialized = {}
    for board, dest in destinations.items():
        project_name = dest.name
        model = copy.deepcopy(baseline)
        model.update(project=project_name, partition_board=board,
                     revision="V2.0-A1_INITIAL_LAYOUT", schematic_revision="V2.0-A1",
                     schematic_date="2026-10-11", baseline_pcb_sha256=PCB_SHA,
                     baseline_CAD_revision="S4.16",
                     baseline_commit="cf54f9970e716272d477afdb252b4e195d595cb6",
                     product_name="Mesh Repeater", product_version="2.0",
                     board_status="INITIAL_PLACEMENT_NOT_ROUTED_NOT_MECHANICALLY_VERIFIED")
        model["status"] = "V2.0 electrical partition with provisional mechanical replacements"
        model["board"].update(width=90, height=60, layers=2, thickness=1.52)
        model["board"]["mounting_holes"] = [{"x": x, "y": y, "drill_mm": 3.2, "net": "GND"} for x, y in HOLES]
        model["assembly_orientation"] = {"native_component_layer": "F.Cu", "assembly_rotation_axis": "X", "assembly_rotation_deg": 0 if board == "POWER" else 180, "components_toward_shield": True, "outside_operator_silk": "B.SilkS" if board == "LOGIC" else "B.SilkS", "CAD_coordinate_note": "Native geometry remains on F; turn upper board in assembly. Do not flip footprints to B and then turn the whole board again."}
        if board == "POWER":
            model["board"]["shield"] = {"x1": 7, "y1": 13.5, "x2": 83, "y2": 56.5, "inside_height": 14, "wall": 0.2, "lid": False, "frame_decision": "retained_initial_layout_subject_to_mechanical_verification"}
            model["board"].pop("antenna_keepout", None)
        else:
            model["board"].pop("shield", None)
        selected = []
        for original in baseline["parts"]:
            allocation = partition[original["ref"]]
            if allocation["board"] != board:
                continue
            p = copy.deepcopy(original)
            p["native_layer"] = "F.Cu"
            p["source_ref"] = p["ref"]
            p["source_revision"] = "S4.16"
            p["source_pose"] = {k: p[k] for k in ["x", "y", "rotation"]}
            row = allocation["assembly_variant_row"]
            p.update(fit_naion=row["Fit_NaIon"] == "yes", fit_lto2s=row["Fit_LTO_2S"] == "yes", fit_naion_no_cold=row["Fit_NaIon_NoCold"] == "yes", value_lto2s=row["Value_LTO_2S"], value_naion_no_cold=row["Value_NaIon_NoCold"], mpn_lto2s=row["MPN_LTO_2S"], mpn_naion_no_cold=row["MPN_NaIon_NoCold"])
            if board == "POWER":
                p["y"] -= 37
            if p["ref"] in {"H1", "H2", "H3", "H4"}:
                index = int(p["ref"][1:]) - 1
                p.update(value="M3 GND contact", nets={"1": "GND"}, footprint="Meshcore:MountingHole_3.2mm_M3_Pad", x=HOLES[index][0], y=HOLES[index][1], rotation=0.0, group="mounting", note="3.2 mm M3 plated/contact mounting hole; exposed GND on both sides. Working return stays in cable.")
            if p["ref"] == "SH1":
                p.update(x=45, y=35, group="shield", note="S4.16 grounded frame retained as initial mechanical option; no lid. Frame outer lines x7..83/y13.5..56.5 mm, wall height14 mm. Validate against new intermediate screen.")
            if p["ref"] in {"J7", "J8", "J12", "J11", "SW1", "SW2"}:
                p["original_mpn"] = p["mpn"]
                p["original_vendor_url"] = p.get("vendor_url", "")
                p["mechanical_selection_status"] = "PENDING_DAN_DRAWING_AND_BOM_CONFIRMATION"
                p["procurement_checked_at"] = None
                p["vendor_url"] = ""
                p["qualification"] = "Initial mechanical replacement; exact mating parts, drawings, availability and footprint verification pending."
                if p["ref"] in {"J7", "J8"}:
                    p.update(footprint="Meshcore:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal", mpn="XH 2-pin right angle candidate", procurement_package="THT XH 1x02 P2.50 side entry candidate")
                elif p["ref"] == "J12":
                    p.update(kind="Connector4", nets={**p["nets"], "4": None}, footprint="Meshcore:JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal", mpn="XH 4-pin right angle candidate", procurement_package="THT XH 1x04 P2.50 side entry candidate", note="LTO ONLY. Original1 BAT/PACK+,2 LTO_MID,3 GND/PACK- preserved. New contact4 deliberately NC. Different-size keyed housing from Na-ion2pin.")
                elif p["ref"] == "J11":
                    p.update(footprint="Meshcore:PinHeader_1x02_P2.54mm_Horizontal", mpn="PLS 1x02 right angle candidate", procurement_package="THT1x02 P2.54 side shunt")
                else:
                    p.update(footprint="Meshcore:SW_TE_1825027_2_Side", mpn="1825027-2", procurement_package="TE side-actuated tactile; drawing footprint pending", note="SPST-NO side actuation. Preserve functional contacts1/2; any mechanical anchors must not alter the electrical contact pair.")
                p["mpn_lto2s"] = p["mpn"]
                p["mpn_naion_no_cold"] = p["mpn"]
            selected.append(p)
        if board == "LOGIC":
            for i, (x, y) in enumerate(HOLES, 201):
                selected.append(add_part(f"H{i}", "MountingHole", "M3 GND contact", {"1": "GND"}, "Meshcore:MountingHole_3.2mm_M3_Pad", x, y, 0.0, "mounting", "M3 screen/standoff GND contact with exposed copper on both sides. Power return remains via cable."))
        connector_ref = "J101" if board == "POWER" else "J201"
        selected.append(add_part(connector_ref, "Connector12", "INTERBOARD 12P", copy.deepcopy(CONTACT_NETS), "Meshcore:IDC-Header_2x06_P2.54mm_Horizontal", 87, 22, 90.0, "interboard", "Provisional12pin polarised side connector.1/3/5/7 FILTER_OUT; all even GND;9 BAT sense;11 MODE. Pin-for-pin cable; no SYS_3V3. Exact selected part/drawing pending."))
        model["parts"] = selected
        model["interboard_connector"] = {"reference": connector_ref, "pin_net_map": CONTACT_NETS, "geometry_status": "PROVISIONAL", "outward_edge": "RIGHT", "continuous_FILTER_OUT_design_A": 0.5, "minimum_single_power_contact_A": 0.5}
        model["assembly_variants_authoritative"] = {p["ref"]: partition[p["ref"]]["assembly_variant_row"] for p in selected if p["ref"] in partition}
        model["assembly_variants_original_summary"] = model.pop("assembly_variants", None)
        model["assembly_variants"] = {
            "default": "Na-ion cold",
            "Na-ion": {"R3_ohm": 61900, "R4_ohm": 100000, "C30": "12pF C0G50V", "charger_nominal_V": baseline["battery_dividers"]["charge_naion"]["cv_typical_V"], "balancer": "DNP", "cold_charge": "FIT R56=1.8R and remaining cold option parts"},
            "Na-ion_NoCold": {"R3_ohm": 61900, "R4_ohm": 100000, "C30": "12pF C0G50V", "balancer": "DNP", "cold_charge": "R56=0R; remaining cold option parts DNP"},
            "LTO_2S": {"R3_ohm": 121000, "R4_ohm": 100000, "C30": "6.8pF C0G50V", "charger_nominal_V": baseline["battery_dividers"]["charge_lto2s"]["cv_typical_V"], "balancer": "FIT", "cold_charge": "R56=0R; remaining cold option parts DNP", "upper_voltage_requirement_V": 5.5, "fault_protection": "none, user-selected S4.16", "balancer_series_ohm": 2},
        }
        dest.mkdir(parents=True, exist_ok=True)
        for name in ["Meshcore.pretty", "3dmodels", "fp-lib-table", "sym-lib-table", "Meshcore.kicad_sym"]:
            copy_if_absent(BASE / name, dest / name)
        copy_if_absent(BASE / "Meshcore_NaIon.kicad_dru", dest / (project_name + ".kicad_dru"))
        for lib, name in [
            ("MountingHole", "MountingHole_3.2mm_M3_Pad"),
            ("Connector_JST", "JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal"),
            ("Connector_JST", "JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal"),
            ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Horizontal"),
            ("Connector_IDC", "IDC-Header_2x06_P2.54mm_Horizontal"),
        ]:
            copy_if_absent(KICAD_FP / (lib + ".pretty") / (name + ".kicad_mod"), dest / "Meshcore.pretty" / (name + ".kicad_mod"))
        write_json(dest / "model.json", model)
        initialized[board] = {"project": project_name, "original_parts": sum(p["ref"] in partition for p in selected), "total_parts": len(selected), "interboard": connector_ref, "position_status": "provisional", "model_sha256": hashlib.sha256((dest / "model.json").read_bytes()).hexdigest()}
    cable = {
        "project": "Mesh Repeater2.0", "revision": "V2_CABLE_A1", "status": "ELECTRICAL_PIN_MAP_FIXED_MECHANICAL_PARTS_PENDING", "date": "2026-10-11", "connector_POWER": "J101", "connector_LOGIC": "J201", "contacts": 12, "cable_route": "Right side outside intermediate90x60 shield; no opening through shield copper", "geometry_status": "Connector mating direction, key and cable-end orientation must be checked against final manufacturer drawing", "connections": [{"net": net, "power": {"ref": "J101", "pin": pin}, "logic": {"ref": "J201", "pin": pin}} for pin, net in CONTACT_NETS.items()], "current_design_A": 0.5, "qualification": "Every individual FILTER_OUT/GND contact rated for full0.5A design load. Four parallel power contacts do not automatically multiply rated current. Check start/load pulse/drop on finished cable.", "SYS_3V3_contact_present": False, "J11": {"board": "LOGIC", "pin1": "FILTER_OUT", "pin2": "SYS_3V3", "no_bypass": True}, "supersedes": "Ten-contact J14/J15 suggestion in electrical partition revision01. Original four logical boundary networks unchanged."}
    write_json(ROOT / "design" / "interboard_cable.json", cable)
    write_json(ROOT / "audit" / "v2_model_seed.json", {"stage": "INITIAL_NOT_FINAL_CAD", "source_pcb_sha256": PCB_SHA, "projects": initialized, "original_refs_allocated": 167, "original_default_values_changed": [], "mechanical_replacements_pending": ["J7", "J8", "J12", "J11", "SW1", "SW2", "J101", "J201"]})
    print(json.dumps(initialized, ensure_ascii=False))


if __name__ == "__main__":
    main()
