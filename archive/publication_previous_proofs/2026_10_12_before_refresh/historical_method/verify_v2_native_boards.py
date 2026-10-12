"""Read-only native PCB/model/XML/variant verification for Mesh Repeater 2.0.

Run with KiCad's Python. Only the requested audit JSON is written, inside V2.
This verifies component and assigned-net identity, not routed continuity, DRC,
manufacturing fitness, EMI, thermal behavior or physical connector mating.
"""
from pathlib import Path
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import xml.etree.ElementTree as ET
import pcbnew as k
from v2_feature_contract import (FEATURE_PATH, PINMAP, NEW_NETS, INA_SOIC_PIN_NAMES, load_feature,
    expected_original_nets, feature_checks, feature_native_checks, legacy_union)

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
BOARDS = {"POWER": "MeshRepeater2_Power", "LOGIC": "MeshRepeater2_Logic"}
LEGACY_CABLE = {str(n): "FILTER_OUT" if n in (1, 3, 5, 7) else "BAT" if n == 9 else "MODE" if n == 11 else "GND" for n in range(1, 13)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xml_data(path):
    tree = ET.parse(path).getroot()
    component_nodes = [n for n in tree.findall("./components/comp") if not n.get("ref", "").startswith("#")]
    components = {n.get("ref"): n for n in component_nodes}
    pin_net, groups = {}, defaultdict(set)
    for net in tree.findall("./nets/net"):
        for node in net.findall("node"):
            if node.get("ref", "").startswith("#"):
                continue
            endpoint = (node.get("ref"), node.get("pin"))
            if endpoint in pin_net:
                raise ValueError("Duplicate native XML pin: " + str(endpoint))
            pin_net[endpoint] = net.get("name")
            groups[net.get("name")].add(endpoint)
    return tree, components, pin_net, groups, Counter(n.get("ref") for n in component_nodes)


def symbol_pins(tree, components, ref):
    source = components[ref].find("libsource")
    library = next(n for n in tree.findall("./libparts/libpart") if n.get("lib") == source.get("lib") and n.get("part") == source.get("part"))
    return {n.get("num"): {"name": n.get("name"), "type": n.get("type")} for n in library.findall("./pins/pin")}


def group_set(groups):
    return {frozenset(nodes) for nodes in groups.values() if nodes}


def group_delta(expected, actual):
    return {"missing_groups": [sorted(n) for n in expected - actual], "extra_groups": [sorted(n) for n in actual - expected]}


class Union:
    def __init__(self):
        self.parents = {}

    def root(self, key):
        self.parents.setdefault(key, key)
        if self.parents[key] != key:
            self.parents[key] = self.root(self.parents[key])
        return self.parents[key]

    def join(self, a, b):
        self.parents[self.root(a)] = self.root(b)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["snapshot", "final"], default="snapshot")
    parser.add_argument("--out", type=Path, default=ROOT / "audit" / "v2_native_boards_snapshot.json")
    args = parser.parse_args()
    args.out = args.out.resolve()
    if not args.out.is_relative_to(ROOT):
        raise ValueError("The audit output must remain inside Mesh_Repeater_2_0")
    contract_path = ROOT / "design" / "v2_electrical_contract.json"
    cable_path = ROOT / "design" / "interboard_cable.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    feature = load_feature(contract_path)
    expected_cable = PINMAP if feature else LEGACY_CABLE
    cable = json.loads(cable_path.read_text(encoding="utf-8"))
    source = {p["reference"]: p for p in contract["parts"]}
    # This immutable copy proves that GPIO *names* still refer to the same
    # physical module pads. Its expected hash is frozen in the V2 contract;
    # the proof is portable and does not depend on the old workspace folders.
    original_xml_path = ROOT / "audit" / "source_s4_16" / "native_netlist.xml"
    paths = [contract_path, cable_path, original_xml_path]
    if feature:
        paths.extend([FEATURE_PATH, ROOT / "tools" / "v2_feature_contract.py"])
    board_inputs = {}
    for board, project in BOARDS.items():
        folder = ROOT / "design" / project
        board_inputs[board] = {"model": folder / "model.json", "pcb": folder / (project + ".kicad_pcb"), "xml": ROOT / "audit" / "schematic" / board / "netlist.xml"}
        paths.extend(board_inputs[board].values())
        variant_report = ROOT / "audit" / (project + "_footprint_variants.json")
        if variant_report.exists():
            board_inputs[board]["graphic_variants"] = variant_report
            paths.append(variant_report)
            evidence = json.loads(variant_report.read_text(encoding="utf-8"))
            paths.extend(ROOT / item["library_file"] for item in evidence.get("maps", []))
    start_hashes = {path: sha(path) for path in paths}
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("original native XML matches frozen hash", start_hashes[original_xml_path] == contract["source_inputs"]["native_netlist"]["sha256"])
    original_xml = xml_data(original_xml_path)
    data, original_seen, removed, all_summary = {}, [], [], {}
    native_union = Union()
    for board, file in board_inputs.items():
        model = json.loads(file["model"].read_text(encoding="utf-8"))
        part_nodes = model["parts"]
        parts = {p["ref"]: p for p in part_nodes}
        native = k.LoadBoard(str(file["pcb"]))
        footprint_nodes = list(native.GetFootprints())
        footprints = {f.GetReference(): f for f in footprint_nodes}
        xml = xml_data(file["xml"])
        graphic_errors = []
        mapped_parts = {ref: part for ref, part in parts.items() if part.get("source_footprint_before_v2_graphic_variant")}
        if mapped_parts:
            evidence = json.loads(file["graphic_variants"].read_text(encoding="utf-8")) if "graphic_variants" in file else {}
            maps = {row["ref"]: row for row in evidence.get("maps", [])}
            if evidence.get("engineering_geometry_and_mpn_values_unchanged") is not True or evidence.get("invariant_before") != evidence.get("invariant_after_with_original_identifiers"):
                graphic_errors.append("Missing exact original-identifier geometry/field invariant proof")
            if set(maps) != set(mapped_parts):
                graphic_errors.append({"mapping_refs": sorted(maps), "model_variant_refs": sorted(mapped_parts)})
            for ref, part in mapped_parts.items():
                row = maps.get(ref, {})
                library_file = ROOT / row.get("library_file", "missing")
                if row.get("approved_selected_footprint") != part["source_footprint_before_v2_graphic_variant"] or row.get("graphic_variant") != part["footprint"] or row.get("same_pads_fab_courtyard_3d_mpn_package") is not True or row.get("normalized_native_geometry_sha256") != row.get("saved_library_geometry_sha256") or not library_file.is_file() or sha(library_file) != row.get("library_sha256"):
                    graphic_errors.append({"ref": ref, "mapping": row})
        check(board + " graphic footprint variants have exact geometry/library mapping proof", not graphic_errors, graphic_errors)
        check(board + " model references unique", all(n == 1 for n in Counter(p["ref"] for p in part_nodes).values()))
        check(board + " PCB references unique", all(n == 1 for n in Counter(f.GetReference() for f in footprint_nodes).values()))
        check(board + " XML references unique", all(n == 1 for n in xml[4].values()))
        check(board + " exact model/PCB/XML reference set", set(parts) == set(footprints) == set(xml[1]), {"model_only_PCB": sorted(set(parts) - set(footprints)), "PCB_only": sorted(set(footprints) - set(parts)), "XML_missing": sorted(set(parts) - set(xml[1])), "XML_extra": sorted(set(xml[1]) - set(parts))})
        expected_groups, pcb_groups = defaultdict(set), defaultdict(set)
        pcb_pin_net, pad_names, pad_count = {}, {}, 0
        metadata_errors, pin_errors, value_errors, variant_errors = [], [], [], []
        for ref, part in parts.items():
            if ref in source:
                original_seen.append(ref)
                original = source[ref]
                check(board + " original allocation " + ref, original["board"] == board)
                old_nets = original["original_model_part"]["nets"]
                allowed_extra = {"4": None} if ref == "J12" else {}
                # The accepted stack explicitly turns the four original
                # mechanical holes into exposed GND-contact mounting lands.
                expected_nets = {"1": "GND"} if ref in {"H1", "H2", "H3", "H4"} and original["original_model_part"]["kind"] == "MountingHole" else expected_original_nets(board, ref, dict(old_nets, **allowed_extra), feature)
                if part["nets"] != expected_nets:
                    pin_errors.append({"reference": ref, "model_nets": part["nets"], "expected": expected_nets})
                row = original["assembly_variant_row"]
                mechanical = original["original_model_part"]["kind"].startswith("Connector") or original["original_model_part"]["kind"] in {"Switch", "MountingHole"}
                fields = [("fit_naion", "Fit_NaIon", True), ("fit_naion_no_cold", "Fit_NaIon_NoCold", True), ("fit_lto2s", "Fit_LTO_2S", True)]
                if not mechanical:
                    fields += [("value", "Value_NaIon", False), ("value_naion_no_cold", "Value_NaIon_NoCold", False), ("value_lto2s", "Value_LTO_2S", False), ("mpn", "MPN_NaIon", False), ("mpn_naion_no_cold", "MPN_NaIon_NoCold", False), ("mpn_lto2s", "MPN_LTO_2S", False)]
                for key, field, is_fit in fields:
                    actual = part.get(key, part.get("value" if key.startswith("value") else "mpn", ""))
                    expected = row[field] == "yes" if is_fit else row[field]
                    if actual != expected:
                        variant_errors.append([ref, key, expected, actual])
            for pin, logical in part["nets"].items():
                group = ("NC", ref, pin) if logical is None else ("NET", logical)
                expected_groups[group].add((ref, str(pin)))
            footprint = footprints.get(ref)
            component = xml[1].get(ref)
            if footprint is None or component is None:
                continue
            library = footprint.GetFPID()
            fp_id = str(library.GetLibNickname()) + ":" + str(library.GetLibItemName())
            actual_meta = {"footprint": fp_id, "value": footprint.GetValue(), "layer": native.GetLayerName(footprint.GetLayer()), "x": k.ToMM(footprint.GetPosition().x), "y": k.ToMM(footprint.GetPosition().y), "rotation": footprint.GetOrientationDegrees() % 360}
            expected_meta = {"footprint": part["footprint"], "value": part["value"], "layer": part.get("native_layer", "F.Cu"), "x": part["x"], "y": part["y"], "rotation": part.get("rotation", 0) % 360}
            if any(actual_meta[n] != expected_meta[n] for n in ["footprint", "value", "layer"]) or any(not math.isclose(actual_meta[n], expected_meta[n], abs_tol=1e-6) for n in ["x", "y", "rotation"]):
                metadata_errors.append({"reference": ref, "expected": expected_meta, "actual": actual_meta})
            if component.findtext("value") != part["value"] or component.findtext("footprint") != part["footprint"]:
                value_errors.append([ref, part["value"], component.findtext("value"), part["footprint"], component.findtext("footprint")])
            numbered = defaultdict(list)
            for pad in footprint.Pads():
                pin = pad.GetNumber()
                if not pin:
                    continue
                numbered[pin].append(pad)
                pad_count += 1
            if set(numbered) != set(part["nets"]):
                pin_errors.append({"reference": ref, "missing_numbered_pads": sorted(set(part["nets"]) - set(numbered)), "unexpected_numbered_pads": sorted(set(numbered) - set(part["nets"]))})
            for pin, pads in numbered.items():
                codes = {p.GetNetCode() for p in pads}
                if len(codes) != 1:
                    pin_errors.append([ref, pin, "duplicate physical pad numbers disagree in net", sorted(codes)])
                    continue
                code = next(iter(codes))
                logical = part["nets"].get(pin)
                net_key = (board, code) if code else (board, "NO_NET", ref, pin)
                pcb_pin_net[(ref, pin)] = net_key
                pad_names[(ref, pin)] = sorted({p.GetNetname() for p in pads})
                pcb_groups[net_key].add((ref, pin))
                native_union.root(net_key)
                if code == 0 and logical is not None:
                    pin_errors.append([ref, pin, "connected functional pad has no assigned PCB net"])
        xml_projected = {name: nodes & set(pcb_pin_net) for name, nodes in xml[3].items()}
        eg, pg, xg = group_set(expected_groups), group_set(pcb_groups), group_set(xml_projected)
        check(board + " numbered pad identities and original pins", not pin_errors, pin_errors)
        check(board + " exact footprint/value/layer/pose vs model", not metadata_errors, metadata_errors)
        check(board + " native XML footprint/value vs model", not value_errors, value_errors)
        check(board + " all original variant Fit/Value/MPN fields", not variant_errors, variant_errors)
        check(board + " PCB assigned endpoint graph vs model", eg == pg, group_delta(eg, pg))
        check(board + " PCB endpoint graph vs native XML", pg == xg and set(pcb_pin_net) == set(xml[2]), {**group_delta(pg, xg), "missing_XML_pins": sorted(set(pcb_pin_net) - set(xml[2])), "extra_XML_pins": sorted(set(xml[2]) - set(pcb_pin_net))})
        data[board] = {"model": model, "parts": parts, "native": native, "footprints": footprints, "xml": xml, "pin_net": pcb_pin_net, "pad_names": pad_names}
        all_summary[board] = {"parts": len(parts), "numbered_physical_pads": pad_count, "unique_ref_pin_pairs": len(pcb_pin_net), "logical_local_groups": len(eg), "native_PCB_groups": len(pg)}
    removed = sorted(set(source) - set(original_seen))
    shield = data["POWER"]["model"].get("board", {}).get("shield", {})
    frame_review_path = ROOT / "audit" / "v2_frame_mount_review.json"
    frame_review = json.loads(frame_review_path.read_text(encoding="utf-8"))
    check("exact documented SH1 mechanical removal", removed == ["SH1"] and shield.get("frame_fitted") is False and frame_review["accepted_decision"]["choice"] == "C", removed)
    check("retained original references allocated once", len(original_seen) == len(set(original_seen)) == 166)
    if feature:
        allowed_new = {"POWER": set(NEW_NETS) | {"J101"}, "LOGIC": {"J201", "H201", "H202", "H203", "H204"}}
        for board in BOARDS:
            extras = set(data[board]["parts"]) - set(source)
            check(board + " exactly authorized additional positions", extras == allowed_new[board], sorted(extras))
        checks.extend(feature_checks({board: d["model"] for board, d in data.items()}, feature))
        ina_names = {pin: fields["name"] for pin, fields in symbol_pins(data["POWER"]["xml"][0], data["POWER"]["xml"][1], "U12").items()} if "U12" in data["POWER"]["xml"][1] else {}
        check("INA219 native SOIC8 physical pin names match TI", ina_names == INA_SOIC_PIN_NAMES, {"expected": INA_SOIC_PIN_NAMES, "actual": ina_names})
    check("no SH1 footprint on either final board", all("SH1" not in d["footprints"] for d in data.values()))
    links = cable.get("connections", [])
    actual_cable = {str(link["power"]["pin"]): link["net"] for link in links}
    check("exact twelve-pin 1:1 interconnect", len(links) == 12 and actual_cable == expected_cable and all(link["power"]["ref"] == "J101" and link["logic"]["ref"] == "J201" and str(link["power"]["pin"]) == str(link["logic"]["pin"]) for link in links))
    cable_errors = []
    for link in links:
        ends = []
        for board, label in [("POWER", "power"), ("LOGIC", "logic")]:
            ref, pin = link[label]["ref"], str(link[label]["pin"])
            part = data[board]["parts"].get(ref)
            net = data[board]["pin_net"].get((ref, pin))
            if not part or part["nets"].get(pin) != link["net"] or net is None:
                cable_errors.append([board, ref, pin, link["net"]])
            ends.append(net)
        if all(ends):
            native_union.join(*ends)
    check("cable endpoints native assigned nets", not cable_errors, cable_errors)
    native_pin_net = {(board, ref, pin): net for board, d in data.items() for (ref, pin), net in d["pin_net"].items()}
    checks.extend(feature_native_checks(native_pin_net, feature))
    # Copy the physical union. R71 is virtually collapsed only in the legacy
    # endpoint projection; model/PCB/XML proofs above preserve both pack nets.
    projected_union = legacy_union(native_union, native_pin_net, feature)
    expected_global, pcb_global = defaultdict(set), defaultdict(set)
    for net in contract["nets"]:
        for node in net["nodes"]:
            ref, pin, board = node["reference"], str(node["pin"]), node["board"]
            if ref in removed or source[ref]["original_model_part"]["kind"] == "MountingHole":
                continue
            expected_global[net["logical_net"]].add((ref, pin))
            native_net = data[board]["pin_net"].get((ref, pin))
            if native_net is not None:
                pcb_global[projected_union.root(native_net)].add((ref, pin))
    eg, pg = group_set(expected_global), group_set(pcb_global)
    check("PCB legacy functional graph equals S4.16 with declared R71 series projection", eg == pg, group_delta(eg, pg))
    logic = data["LOGIC"]
    for ref in ["M1", "M2"]:
        old_pin_names = symbol_pins(original_xml[0], original_xml[1], ref)
        new_pin_names = symbol_pins(logic["xml"][0], logic["xml"][1], ref)
        check("FakeTec unchanged physical pin/GPIO names " + ref, new_pin_names == old_pin_names, {"baseline": old_pin_names, "V2_native_XML": new_pin_names})
    check("J11 assigned FILTER_OUT remains distinct from SYS_3V3", logic["parts"]["J11"]["nets"] == {"1": "FILTER_OUT", "2": "SYS_3V3"} and logic["pin_net"][("J11", "1")] != logic["pin_net"][("J11", "2")] and native_union.root(logic["pin_net"][("J11", "1")]) != native_union.root(logic["pin_net"][("J11", "2")]))
    j10 = logic["parts"]["J10"]
    old_j10 = source["J10"]["original_model_part"]
    j10_selected_footprint = j10.get("source_footprint_before_v2_graphic_variant", j10["footprint"])
    check("J10 original ISP pose and physical footprint retained", all(j10[key] == old_j10[key] for key in ["x", "y", "rotation"]) and j10_selected_footprint == old_j10["footprint"])
    check("both board copper counts and thickness match models", all(d["native"].GetCopperLayerCount() == d["model"]["board"]["layers"] and math.isclose(k.ToMM(d["native"].GetDesignSettings().GetBoardThickness()), d["model"]["board"]["thickness"], abs_tol=1e-6) for d in data.values()))
    changed = [str(path) for path in paths if sha(path) != start_hashes[path]]
    check("input snapshot remained unchanged during read-only review", not changed, changed)
    report = {"stage": args.stage.upper() + "_NATIVE_ASSIGNED_NET_IDENTITY_ONLY", "ok": all(c["pass"] for c in checks), "source_commit": contract["published_source_commit"], "scope": "Saved native component/pad/ref/value/variant/GPIO/assigned-net identity against model, native XML and frozen S4.16. No routing-continuity, DRC, thermal, EMI or physical-mating claim.", "CAD_files_modified": False, "summary": all_summary, "checks": checks, "inputs": {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else "read_only_original_workspace/" + str(path.relative_to(WORKSPACE)): digest for path, digest in start_hashes.items()}, "mechanical_removal_proof": {"path": str(frame_review_path.relative_to(ROOT)), "sha256": sha(frame_review_path)}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "stage": report["stage"], "checks": len(checks), "failed": [c for c in checks if not c["pass"]], "report": str(args.out.relative_to(ROOT))}, ensure_ascii=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
