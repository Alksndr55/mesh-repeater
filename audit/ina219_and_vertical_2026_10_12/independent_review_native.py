"""Independent saved-native review; never SaveBoard, refill or edit CAD.

--scope partial reads LOGIC/SHIELD only; --scope final is reserved for the
root FINAL_FILES_READY handoff. It writes its own audit JSON and CLI DRC files.
"""
from pathlib import Path
import argparse, csv, hashlib, json, math, runpy, subprocess, sys
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/cad")]
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from v2_feature_contract import PINMAP, INA_SOIC_PIN_NAMES, load_feature, feature_native_checks
from audit_v2_routing_engineering import TraceGraph
from verify_v2_native_boards import xml_data, symbol_pins, group_set, group_delta

HELD = []
CLI = Path(sys.executable).parent / "kicad-cli.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xy(point):
    return [round(k.ToMM(point.x), 6), round(k.ToMM(point.y), 6)]


def pad_map(fp):
    out = defaultdict(list)
    for p in fp.Pads():
        if p.GetNumber():
            out[p.GetNumber()].append({"at": xy(p.GetPosition()), "size": xy(p.GetSize()), "drill": xy(p.GetDrillSize()), "rotation": p.GetOrientationDegrees() % 360, "attribute": int(p.GetAttribute()), "shape": int(p.GetShape()), "net": p.GetNetname()})
    return {key: sorted(value, key=lambda item: item["at"]) for key, value in out.items()}


def pose(fp):
    return {"at": xy(fp.GetPosition()), "angle": fp.GetOrientationDegrees() % 360, "layer": int(fp.GetLayer())}


def run_drc(path, scope, board):
    destination = OUT / ("independent_" + scope + "_" + board + "_drc.json")
    command = [str(CLI), "pcb", "drc", "--format", "json", "--all-track-errors", "--severity-all", "--exit-code-violations", "--output", str(destination)]
    if board != "SHIELD":
        command.append("--schematic-parity")
    command.append(str(path))
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not destination.exists():
        raise RuntimeError(completed.stdout + completed.stderr)
    result = json.loads(destination.read_text(encoding="utf-8-sig"))
    counts = {name: len(result.get(name, [])) for name in ("violations", "unconnected_items", "schematic_parity", "ignored_checks")}
    return {"path": destination.relative_to(ROOT).as_posix(), "sha256": sha(destination), "returncode": completed.returncode, "counts": counts, "pass": completed.returncode == 0 and not any(counts.values())}


def physical_ground(board):
    """Normalize native fractured fills before union; join only plated barrels."""
    ground, items = {}, list(board.GetTracks()) + [p for f in board.GetFootprints() for p in f.Pads()]
    for layer in (k.F_Cu, k.B_Cu):
        copper = k.SHAPE_POLY_SET()
        for zone in board.Zones():
            if not zone.GetIsRuleArea() and zone.GetNetname() == "GND" and zone.HasFilledPolysForLayer(layer):
                shape = zone.GetFilledPolysList(layer)
                shape.Unfracture()
                copper.BooleanAdd(shape)
        for item in items:
            if item.GetNetname() != "GND" or not item.IsOnLayer(layer):
                continue
            if isinstance(item, k.PAD):
                shape = item.GetEffectivePolygon(layer)
            else:
                shape = k.SHAPE_POLY_SET()
                item.TransformShapeToPolygon(shape, layer, 0, 1000, k.ERROR_OUTSIDE)
            shape.Unfracture()
            copper.BooleanAdd(shape)
        copper.Unfracture()
        ground[layer] = copper
    islands = {}
    for layer, copper in ground.items():
        for i in range(copper.OutlineCount()):
            poly = k.SHAPE_POLY_SET(); poly.AddOutline(copper.COutline(i))
            for h in range(copper.HoleCount(i)):
                poly.AddHole(copper.CHole(i, h), 0)
            islands[(layer, i)] = poly
    edges = defaultdict(set)
    for item in items:
        if item.GetNetname() != "GND" or not (isinstance(item, k.PCB_VIA) or isinstance(item, k.PAD) and item.GetAttribute() == k.PAD_ATTRIB_PTH):
            continue
        touches = [key for key, poly in islands.items() if item.IsOnLayer(key[0]) and poly.Contains(item.GetPosition())]
        for a in touches:
            edges[a].update(touches)
    remaining, components = set(islands), []
    while remaining:
        start = next(iter(remaining)); seen = {start}; queue = [start]
        while queue:
            at = queue.pop()
            for other in edges[at]:
                if other not in seen:
                    seen.add(other); queue.append(other)
        remaining -= seen
        components.append({"islands": [{"layer": board.GetLayerName(layer), "index": index, "area_mm2": islands[(layer, index)].Area() / 1e12} for layer, index in sorted(seen)]})
    return ground, components


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("partial", "final"), default="partial")
    args = parser.parse_args()
    inputs, checks, data = {}, [], {}

    def bind(path):
        inputs[path.relative_to(ROOT).as_posix()] = sha(path)

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    contract_path = ROOT / "design/v2_electrical_contract.json"
    for code_path in (Path(__file__), ROOT / "tools/v2_feature_contract.py", ROOT / "tools/audit_v2_routing_engineering.py", ROOT / "tools/verify_v2_native_boards.py"):
        bind(code_path)
    feature = load_feature(contract_path)
    bind(contract_path); bind(ROOT / "design/feature_ina219_vertical.json")
    baseline_path = ROOT / "baseline/S4_16/Meshcore_NaIon.kicad_pcb"
    bind(baseline_path)
    baseline = k.LoadBoard(str(baseline_path)); HELD.append(baseline)
    baseline_fp = {f.GetReference(): f for f in baseline.GetFootprints()}
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    check("Frozen actual S4.16 PCB hash matches immutable source", sha(baseline_path) == contract["source_inputs"]["pcb"]["sha256"])
    boards = ("LOGIC", "SHIELD") if args.scope == "partial" else ("POWER", "LOGIC", "SHIELD")
    drc = {}
    for board in boards:
        project = "MeshRepeater2_" + board.title()
        path = ROOT / "design" / project / (project + ".kicad_pcb")
        bind(path)
        native = k.LoadBoard(str(path)); HELD.append(native)
        fps = {f.GetReference(): f for f in native.GetFootprints()}
        data[board] = {"board": native, "fps": fps, "path": path}
        drc[board] = run_drc(path, args.scope, board)
        bind(ROOT / drc[board]["path"])
        check(board + " fresh independent strict DRC", drc[board]["pass"], drc[board])
        if board != "SHIELD":
            xml_path = ROOT / "audit/schematic" / board / "netlist.xml"
            bind(xml_path)
            native_xml = xml_data(xml_path)
            data[board]["xml"] = native_xml
            actual = defaultdict(set)
            pin_net = {}
            for ref, fp in fps.items():
                for pad in fp.Pads():
                    pin = pad.GetNumber()
                    if not pin:
                        continue
                    group = (board, pad.GetNetCode()) if pad.GetNetCode() else (board, "NC", ref, pin)
                    actual[group].add((ref, pin))
                    pin_net[(board, ref, pin)] = group
            expected = group_set(native_xml[3]); physical = group_set(actual)
            check(board + " direct saved PCB endpoint groups equal exported native XML", expected == physical and set(native_xml[1]) == set(fps), group_delta(expected, physical))
            data[board]["pin_net"] = pin_net
            data[board]["graph"] = TraceGraph(native)

    logic = data["LOGIC"]
    common_logic_refs = set(baseline_fp) & set(logic["fps"])

    def projected_groups(fps):
        groups = defaultdict(set)
        by_endpoint = {}
        for ref in common_logic_refs:
            for pad in fps[ref].Pads():
                if pad.GetNumber():
                    code = pad.GetNetCode() if pad.GetNetCode() else ("NC", ref, pad.GetNumber())
                    groups[code].add((ref, pad.GetNumber()))
                    by_endpoint[(ref, pad.GetNumber())] = code
        return {endpoint: sorted(groups[code]) for endpoint, code in by_endpoint.items()}

    baseline_groups = projected_groups(baseline_fp)
    current_groups = projected_groups(logic["fps"])

    for ref in ("M1", "M2", "J10"):
        old, current = baseline_fp[ref], logic["fps"][ref]
        old_pads, new_pads = pad_map(old), pad_map(current)
        # Sheet-path prefixes are allowed to change. Physical pads and the
        # original endpoints actually joined by native copper/net identity are
        # compared directly; no authoring model supplies this expectation.
        def geometry_only(pads):
            return {pin: [{key: value for key, value in row.items() if key != "net"} for row in rows] for pin, rows in pads.items()}
        membership = {pin: {"baseline": baseline_groups[(ref, pin)], "current": current_groups.get((ref, pin))} for pin in old_pads}
        check(ref + " actual native pose/pad geometry and projected original endpoint groups preserved", pose(old) == pose(current) and geometry_only(old_pads) == geometry_only(new_pads) and all(x["baseline"] == x["current"] for x in membership.values()), {"baseline_pose": pose(old), "current_pose": pose(current), "baseline_pad_map": old_pads, "current_pad_map": new_pads, "direct_native_endpoint_memberships": membership, "sheet_path_renaming_is_not_GPIO_reassignment": True})
    original_xml_path = ROOT / "audit/source_s4_16/native_netlist.xml"
    bind(original_xml_path)
    original_xml = xml_data(original_xml_path)
    check("Frozen GPIO-symbol source XML hash", sha(original_xml_path) == contract["source_inputs"]["native_netlist"]["sha256"])
    for ref in ("M1", "M2"):
        a = symbol_pins(original_xml[0], original_xml[1], ref)
        b = symbol_pins(logic["xml"][0], logic["xml"][1], ref)
        check(ref + " physical pin numbers retain exact GPIO names/types in native symbols", a == b, {"baseline": a, "current": b})

    # The old five corrections are compared against their actual saved PCB,
    # not against the new authoring model or a copied assessment.
    prior_path = ROOT / "audit/ina219_and_vertical_2026_10_12/before/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb"
    if not prior_path.exists():
        prior_path = ROOT / "audit/ina219_vertical_interconnect_2026_10_12/MeshRepeater2_Logic_before.kicad_pcb"
    bind(prior_path)
    prior = k.LoadBoard(str(prior_path)); HELD.append(prior)
    old_review = ROOT / "audit/fixes_2026_10_12/reviewer.json"; bind(old_review)
    check("Previously corrected actual LOGIC archive matches prior reviewed SHA", sha(prior_path) == json.loads(old_review.read_text(encoding="utf-8"))["native_LOGIC_sha256"])

    frozen_net_aliases = {pin["native_net"]: pin["logical_net"] for part in contract["parts"] for pin in part["exact_netpins"].values()}

    def traces(board, nets):
        result = []
        for t in board.GetTracks():
            if frozen_net_aliases.get(t.GetNetname(), t.GetNetname().split("/")[-1]) not in nets:
                continue
            if isinstance(t, k.PCB_VIA):
                row = ("via", frozen_net_aliases.get(t.GetNetname(), t.GetNetname().split("/")[-1]), tuple(xy(t.GetPosition())), k.ToMM(t.GetDrill()), k.ToMM(t.GetWidth(k.F_Cu)))
            else:
                row = ("track", frozen_net_aliases.get(t.GetNetname(), t.GetNetname().split("/")[-1]), tuple(xy(t.GetStart())), tuple(xy(t.GetEnd())), k.ToMM(t.GetWidth()), int(t.GetLayer()))
            result.append(row)
        return sorted(result)

    preserved_nets = {"MOSI_RF", "MISO_MCU", "RADIO_RST", "RADIO_RXEN", "ANT_RF", "ANT_SMA"}
    old_geometry, now_geometry = traces(prior, preserved_nets), traces(logic["board"], preserved_nets)
    check("Prior short SPI/RESET and repaired RXEN/RF geometry retained", old_geometry == now_geometry, {"old_items": len(old_geometry), "new_items": len(now_geometry), "old_only": [x for x in old_geometry if x not in now_geometry], "new_only": [x for x in now_geometry if x not in old_geometry]})
    for ref in ("H201", "H202", "H203", "H204"):
        pads = list(logic["fps"][ref].Pads())
        check(ref + " PTH GND contact retains3.2mm drill and6mm copper", bool(pads) and all(p.GetAttribute() == k.PAD_ATTRIB_PTH and p.GetNetname() == "GND" and xy(p.GetSize()) == [6.0, 6.0] and xy(p.GetDrillSize()) == [3.2, 3.2] for p in pads))

    old_models_path = ROOT / "audit/fixes_2026_10_12/reviewer_models.json"
    bind(old_models_path)
    old_models = json.loads(old_models_path.read_text(encoding="utf-8"))
    switch_record = next(row for row in old_models["switch_models"] if "Logic" in row["path"])
    switch_path = ROOT / switch_record["path"].replace("\\", "/")
    bind(switch_path)
    check("Corrected8.41mm TE switch STEP retained byte-for-byte", sha(switch_path) == switch_record["sha256"] and math.isclose(switch_record["bracket_width_mm"], 8.41, abs_tol=1e-6), {"path": switch_path.relative_to(ROOT).as_posix(), "prior_independently_measured_bracket_mm": switch_record["bracket_width_mm"]})
    buy_path = ROOT / "bom/DAN_NEW_PARTS.csv"; bind(buy_path)
    buying = {row["Refs"]: row for row in csv.DictReader(buy_path.open(encoding="utf-8-sig"))}
    housings, contacts = buying.get("J3_J5_HOUSINGS", {}), buying.get("J3_J5_CONTACTS", {})
    check("Prior J3/J5 mate-housing and contact BOM correction retained", housings.get("MPN") == "Connfly I-DS1071-SCB01x4" and housings.get("Quantity_per_assembly") == "2" and contacts.get("MPN") == "Connfly T-DS1071-SC600" and contacts.get("Quantity_per_assembly") == "8")

    new_track_angles = []
    prior_track_ids = {str(t.m_Uuid.AsString()) for t in prior.GetTracks()}
    for track in logic["board"].GetTracks():
        if isinstance(track, k.PCB_VIA) or str(track.m_Uuid.AsString()) in prior_track_ids:
            continue
        a, b = track.GetStart(), track.GetEnd()
        dx, dy = abs(a.x - b.x), abs(a.y - b.y)
        if dx > 2 and dy > 2 and abs(dx - dy) > 2:
            new_track_angles.append({"start": xy(a), "end": xy(b), "net": track.GetNetname()})
    check("New LOGIC interconnect tracks use straight0/45/90degree segments", not new_track_angles, new_track_angles)

    ground, components = physical_ground(logic["board"])
    check("LOGIC ground physically forms one connected copper component across plated barrels", len(components) == 1, {"components": components, "method": "Normalize fractured saved fills before Boolean union; actual plated GND barrels bridge layers; no refill or save"})
    rf_missing = []
    for track in logic["board"].GetTracks():
        if isinstance(track, k.PCB_VIA) or track.GetNetname().split("/")[-1] != "ANT_RF":
            continue
        other = k.B_Cu if track.GetLayer() == k.F_Cu else k.F_Cu
        steps = max(1, math.ceil(k.ToMM(track.GetLength()) / .025))
        a, b = track.GetStart(), track.GetEnd()
        for i in range(steps + 1):
            point = k.VECTOR2I(round(a.x + (b.x - a.x) * i / steps), round(a.y + (b.y - a.y) * i / steps))
            if not ground[other].Contains(point):
                rf_missing.append(xy(point))
    check("Repaired ANT_RF axis retains actual opposite-layer ground after fill normalization", not rf_missing, {"sample_pitch_mm": .025, "missing_samples": rf_missing})
    for pin in ("2", "4", "6", "8"):
        pad = next(p for p in logic["fps"]["J201"].Pads() if p.GetNumber() == pin)
        linked = logic["board"].GetConnectivity().GetConnectedItems(pad)
        check("J201." + pin + " working GND contact reaches native local ground fill", pad.GetNetname() == "GND" and any(isinstance(z, k.ZONE) and z.GetNetname() == "GND" and not z.GetIsRuleArea() for z in linked))

    paths = {}
    pairs = {"filtered1": (("J201", "1"), ("J11", "1")), "filtered3": (("J201", "3"), ("J11", "1")), "filtered5": (("J201", "5"), ("J11", "1")), "INA_supply_return": (("J11", "2"), ("J201", "7")), "battery_sense": (("J201", "9"), ("R27", "1")), "SDA": (("M1", "15"), ("J201", "10")), "SCL": (("M1", "16"), ("J201", "12")), "MCU_supply": (("J11", "2"), ("M1", "9")), "modem_branch": (("J11", "2"), ("FB1", "1")), "modem_bypass": (("M2", "3"), ("C23", "1"))}
    for name, ends in pairs.items():
        paths[name] = logic["graph"].path(*ends, .001 if name == "INA_supply_return" else .5 if "supply" in name or name.startswith("filtered") or "modem" in name else 0)
        check("LOGIC direct copper route " + name, paths[name]["found_without_zones"], paths[name])
    shared = set(paths["MCU_supply"].get("track_UUIDs", [])) & set(paths["modem_branch"].get("track_UUIDs", []))
    check("MCU and modem positive branches have no common selected trace segments", not shared, sorted(shared))
    check("J11 removed leaves native FILTER_OUT and SYS_3V3 distinct", next(p for p in logic["fps"]["J11"].Pads() if p.GetNumber() == "1").GetNetCode() != next(p for p in logic["fps"]["J11"].Pads() if p.GetNumber() == "2").GetNetCode())

    shield = data["SHIELD"]
    holes = list(shield["fps"]["HS1"].Pads())
    hole_positions = sorted(xy(p.GetPosition()) for p in holes)
    logic_positions = sorted(xy(p.GetPosition()) for p in logic["fps"]["J201"].Pads())
    check("Twelve shield drill centres match actual LOGIC socket pad centres", len(holes) == len(logic_positions) == 12 and hole_positions == logic_positions, {"shield_native": hole_positions, "LOGIC_native": logic_positions})
    check("Shield signal apertures are NPTH2mm without net assignment", all(p.GetAttribute() == k.PAD_ATTRIB_NPTH and xy(p.GetDrillSize()) == [2.0, 2.0] and p.GetNetCode() == 0 for p in holes))
    foil_zones = [zone for zone in shield["board"].Zones() if not zone.GetIsRuleArea() and zone.GetNetname() == "GND" and zone.HasFilledPolysForLayer(k.F_Cu)]
    check("Screen has exactly one saved front GND fill", len(foil_zones) == 1)
    # Filled KiCad polygons are fractured. Unfracture the saved single-zone
    # shape before interpreting holes; BooleanAdd on fractured input can lose
    # void boundaries. No refill or SaveBoard is performed.
    foil = foil_zones[0].GetFilledPolysList(k.F_Cu)
    foil.Unfracture()
    check("Saved screen front foil remains one connected region", foil.OutlineCount() == 1, {"regions": foil.OutlineCount(), "holes": foil.HoleCount(0) if foil.OutlineCount() else 0})
    contours = []
    for index in range(foil.OutlineCount()):
        contours.append(foil.COutline(index))
        contours.extend(foil.CHole(index, hole) for hole in range(foil.HoleCount(index)))

    def edge_distance(point, contour):
        points = [xy(contour.CPoint(i)) for i in range(contour.PointCount())]
        distances = []
        for a, b in zip(points, points[1:] + points[:1]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            norm = dx * dx + dy * dy
            fraction = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / norm)) if norm else 0
            distances.append(math.dist(point, [a[0] + fraction * dx, a[1] + fraction * dy]))
        return min(distances)

    def in_copper(point):
        return any(foil.COutline(i).PointInside(point) and not any(foil.CHole(i, h).PointInside(point) for h in range(foil.HoleCount(i))) for i in range(foil.OutlineCount()))

    gaps = [(-1 if in_copper(p.GetPosition()) else min(edge_distance(xy(p.GetPosition()), c) for c in contours)) - k.ToMM(p.GetDrillSize().x) / 2 for p in holes]
    check("Actual saved foil stays at least0.50mm from every signal drill", bool(gaps) and min(gaps) >= .5 - 1e-6, gaps)
    check("Screen has no tracks and no back copper fill", not list(shield["board"].GetTracks()) and not any(z.HasFilledPolysForLayer(k.B_Cu) and z.GetFilledPolysList(k.B_Cu).Area() > 0 for z in shield["board"].Zones() if not z.GetIsRuleArea()))

    if args.scope == "final":
        power = data["POWER"]
        native_pin_net = {endpoint: group for board in ("POWER", "LOGIC") for endpoint, group in data[board]["pin_net"].items()}
        checks.extend(feature_native_checks(native_pin_net, feature))
        actual_ina = {pin: row["name"] for pin, row in symbol_pins(power["xml"][0], power["xml"][1], "U12").items()}
        check("INA219 actual SOIC8 native symbol pin numbering", actual_ina == INA_SOIC_PIN_NAMES, actual_ina)
        check("INA219 address0x40 straps and ground are native GND", all(next(p for p in power["fps"]["U12"].Pads() if p.GetNumber() == pin).GetNetname() == "GND" for pin in ("1", "2", "6")))
        check("Actual R71 is0.1ohm1percent1W and distinct from original charging shunt", power["fps"]["R71"].GetValue() == "0.1R 1% 1W" and power["fps"]["R1"].GetValue().startswith("0.28"), {"R71": power["fps"]["R71"].GetValue(), "R1": power["fps"]["R1"].GetValue()})
        sys_code = next(p for p in power["fps"]["U12"].Pads() if p.GetNumber() == "5").GetNetCode()
        sys_nodes = {(ref, p.GetNumber()) for ref, fp in power["fps"].items() for p in fp.Pads() if p.GetNumber() and p.GetNetCode() == sys_code}
        check("Actual returned SYS copper group has only J101.7 U12.5 C63.1", sys_nodes == {("J101", "7"), ("U12", "5"), ("C63", "1")}, sorted(sys_nodes))
        power_ground, power_components = physical_ground(power["board"])
        check("POWER ground physically forms one connected copper component", len(power_components) == 1, power_components)
        for pin in ("2", "4", "6", "8"):
            pad = next(p for p in power["fps"]["J101"].Pads() if p.GetNumber() == pin)
            linked = power["board"].GetConnectivity().GetConnectedItems(pad)
            check("J101." + pin + " local GND return independent of external standoffs", pad.GetNetname() == "GND" and any(isinstance(z, k.ZONE) and z.GetNetname() == "GND" and not z.GetIsRuleArea() for z in linked))
        power_pairs = {
            "battery_to_shunt_RAW": (("J8", "1"), ("R71", "2"), 1.25),
            "shunt_SYS_to_C53": (("R71", "1"), ("C53", "1"), 1.25),
            "C53_to_TPS_VIN": (("C53", "1"), ("U2", "10"), 1.25),
            "raw_battery_to_ADC_sense_pin": (("J8", "1"), ("J101", "9"), 0),
            "Kelvin_positive": (("R71", "1"), ("R72", "1"), 0),
            "Kelvin_negative": (("R71", "2"), ("R73", "1"), 0),
            "RC_positive_to_INA": (("R72", "2"), ("U12", "8"), 0),
            "RC_negative_to_INA": (("R73", "2"), ("U12", "7"), 0),
            "SYS_return_to_C63": (("J101", "7"), ("C63", "1"), .001),
            "C63_to_INA_VS": (("C63", "1"), ("U12", "5"), .001),
            "SDA_to_INA": (("J101", "10"), ("U12", "3"), 0),
            "SCL_to_INA": (("J101", "12"), ("U12", "4"), 0),
            "TPS_input_bypass": (("C12", "1"), ("U2", "10"), 1.25),
            "TPS_output_bypass": (("U2", "6"), ("C14", "1"), .5),
        }
        power_paths = {}
        for name, (start, end, current) in power_pairs.items():
            power_paths[name] = power["graph"].path(start, end, current)
            check("POWER direct copper route " + name, power_paths[name]["found_without_zones"], power_paths[name])

        duplicates, seen_geometry, bad_angles = [], {}, []
        for name in ("POWER", "LOGIC", "SHIELD"):
            seen_geometry.clear()
            for item in data[name]["board"].GetTracks():
                if isinstance(item, k.PCB_VIA):
                    key = ("via", tuple(xy(item.GetPosition())), item.GetNetCode(), item.GetDrill(), item.GetWidth(k.F_Cu), item.GetLayerSet().FmtHex())
                else:
                    key = ("track", tuple(sorted((tuple(xy(item.GetStart())), tuple(xy(item.GetEnd()))))), item.GetNetCode(), item.GetWidth(), int(item.GetLayer()))
                    if name == "POWER":
                        a, b = item.GetStart(), item.GetEnd()
                        dx, dy = abs(a.x - b.x), abs(a.y - b.y)
                        if dx > 2 and dy > 2 and abs(dx - dy) > 2:
                            bad_angles.append({"net": item.GetNetname(), "start": xy(a), "end": xy(b)})
                if key in seen_geometry:
                    duplicates.append({"board": name, "geometry": str(key), "first_UUID": seen_geometry[key], "duplicate_UUID": item.m_Uuid.AsString()})
                else:
                    seen_geometry[key] = item.m_Uuid.AsString()
        check("Actual native boards contain no exact duplicate tracks or vias", not duplicates, duplicates)
        check("Actual POWER tracks all use straight0/45/90degree segments", not bad_angles, bad_angles)

        def route_copper(path, layer):
            result = k.SHAPE_POLY_SET()
            for uuid in path["track_UUIDs"]:
                item = power["graph"].items[uuid]
                if item.IsOnLayer(layer):
                    shape = k.SHAPE_POLY_SET()
                    item.TransformShapeToPolygon(shape, layer, 0, 1000, k.ERROR_OUTSIDE)
                    shape.Unfracture()
                    result.BooleanAdd(shape)
            result.Unfracture()
            return result

        for name, main, pin in (("Kelvin_positive", "shunt_SYS_to_C53", "1"), ("Kelvin_negative", "battery_to_shunt_RAW", "2")):
            pad = next(p for p in power["fps"]["R71"].Pads() if p.GetNumber() == pin)
            overlap = []
            for layer in (k.F_Cu, k.B_Cu):
                sense = route_copper(power_paths[name], layer)
                feed = route_copper(power_paths[main], layer)
                common = k.SHAPE_POLY_SET()
                common.BooleanIntersection(sense, feed)
                pad_shape = pad.GetEffectivePolygon(layer)
                pad_shape.Unfracture()
                common.BooleanSubtract(pad_shape)
                common.Unfracture()
                overlap.append({"layer": power["board"].GetLayerName(layer), "sense_and_power_common_copper_outside_R71_pad_mm2": common.Area() / 1e12})
            check("Actual " + name + " separates sensing and power copper outside shunt pad", all(x["sense_and_power_common_copper_outside_R71_pad_mm2"] < 1e-6 for x in overlap), {"method": "Actual selected native route polygons intersected layer-by-layer, with the actual R71 pad polygon subtracted; no copied model or idealized line-only overlap.", "overlap": overlap})
        check("Battery RAW cannot reach TPS VIN through bare copper without R71", not power["graph"].path(("J8", "1"), ("U2", "10"), 1.25)["found_without_zones"])
        filtered_end = ("L4", "2")
        for pin in ("1", "3", "5"):
            route = power["graph"].path(filtered_end, ("J101", pin), .5)
            check("Lower final LC stage reaches FILTER_OUT pin" + pin, route["found_without_zones"], route)
        check("Final LC stage cannot reach returned SYS pin7 without J11", not power["graph"].path(filtered_end, ("J101", "7"), .001)["found_without_zones"])
        physical_match = []
        for pin, net in PINMAP.items():
            a = next(p for p in power["fps"]["J101"].Pads() if p.GetNumber() == pin)
            b = next(p for p in logic["fps"]["J201"].Pads() if p.GetNumber() == pin)
            point = xy(b.GetPosition()); point[1] = round(60 - point[1], 6)
            physical_match.append({"pin": pin, "net": net, "POWER_xy": xy(a.GetPosition()), "LOGIC_after_X180_xy": point, "pass": xy(a.GetPosition()) == point})
        check("All12 actual pad centres mate1:1 after LOGIC flip", all(x["pass"] for x in physical_match), physical_match)

    changed = [path for path, digest in inputs.items() if sha(ROOT / path) != digest]
    check("Input native snapshot unchanged by independent read-only review", not changed, changed)
    report = {"ok": args.scope == "final" and all(x["pass"] for x in checks), "stage": "PARTIAL_LOGIC_SHIELD_NOT_FINAL" if args.scope == "partial" else "FINAL_SAVED_NATIVE_REVIEW", "checks": checks, "inputs": inputs, "native_CAD_modified": False, "measurements": {"LOGIC_paths": paths, "POWER_paths": power_paths if args.scope == "final" else None}, "remaining_physical_checks": ["Actual generic Ali mating depth, male section/straightness and pin-to-screen clearance under assembly tolerances.", "INA219 current calibration, voltage offset from input filter, actual0.1ohm shunt TCR/temperature and continuous-mode battery consumption.", "Modem/MCU supply transients, RF/SPI operation and EMI measurements; native geometry/DRC do not qualify those.", "Accepted inherited LTO2ohm LMV431 current and battery-absent CN3722/TPS63802 overvoltage limitations remain."]}
    destination = OUT / ("independent_partial_review.json" if args.scope == "partial" else "independent_final_native_measurements.json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stage": report["stage"], "passed": sum(x["pass"] for x in checks), "total": len(checks), "failed": [x for x in checks if not x["pass"]], "report": destination.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    if any(not x["pass"] for x in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
