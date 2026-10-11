"""Read-only dimensional routing audit. Writes JSON; never saves a PCB.

Resistance is an estimate along one route through complete native segments,
not a field solver, ampacity certification, transient analysis or EMC test.
Via.GetWidth() is always called with an explicit copper layer.
"""
from pathlib import Path
from collections import defaultdict
import hashlib
import heapq
import json
import math
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
RHO20 = 1.724e-8
COPPER_M = 35e-6
VIA_WALL_M = 20e-6


def mm(p):
    return [round(k.ToMM(p.x), 6), round(k.ToMM(p.y), 6)]


def uid(item):
    return str(item.m_Uuid.AsString())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def intersection_area(a, b):
    out = k.SHAPE_POLY_SET()
    out.BooleanIntersection(a, b)
    return out.Area() / 1e12


class TraceGraph:
    def __init__(self, board):
        self.board = board
        self.items = {uid(t): t for t in board.GetTracks()}
        self.pads = defaultdict(list)
        self.labels = {}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNumber():
                    self.items[uid(p)] = p
                    self.pads[(fp.GetReference(), p.GetNumber())].append(uid(p))
                    self.labels[uid(p)] = [fp.GetReference(), p.GetNumber()]
        self.weights = {}
        self.edges = defaultdict(set)
        height_m = k.ToMM(board.GetDesignSettings().GetBoardThickness()) / 1000
        for key, item in self.items.items():
            if isinstance(item, k.PCB_VIA):
                diameter_m = k.ToMM(item.GetDrill()) / 1000
                self.weights[key] = RHO20 * height_m / (math.pi * diameter_m * VIA_WALL_M)
            elif isinstance(item, k.PCB_TRACK):
                self.weights[key] = RHO20 * (k.ToMM(item.GetLength()) / 1000) / (k.ToMM(item.GetWidth()) / 1000 * COPPER_M)
            else:
                self.weights[key] = 0
            conn = board.GetConnectivity()
            for neighbor in list(conn.GetConnectedTracks(item)) + list(conn.GetConnectedPads(item)):
                nk = uid(neighbor)
                if nk in self.items and neighbor.GetNetCode() == item.GetNetCode():
                    self.edges[key].add(nk)
                    self.edges[nk].add(key)

    def path(self, start, end, current_A, banned=None):
        banned = set(banned or [])
        start, end = tuple(start), tuple(end)
        sources = self.pads[start]
        targets = set(self.pads[end])
        queue = [(0, node) for node in sources]
        distances = {n: 0 for n in sources}
        previous = {}
        finish = None
        while queue:
            value, node = heapq.heappop(queue)
            if value != distances[node]:
                continue
            if node in targets:
                finish = node
                break
            for neighbor in self.edges[node]:
                if neighbor in banned:
                    continue
                added = (self.weights[node] + self.weights[neighbor]) / 2
                candidate = value + added
                if candidate < distances.get(neighbor, math.inf):
                    distances[neighbor] = candidate
                    previous[neighbor] = node
                    heapq.heappush(queue, (candidate, neighbor))
        if finish is None:
            return {"start": start, "end": end, "found_without_zones": False}
        route = [finish]
        while route[-1] in previous:
            route.append(previous[route[-1]])
        route.reverse()
        tracks = [self.items[n] for n in route if isinstance(self.items[n], k.PCB_TRACK) and not isinstance(self.items[n], k.PCB_VIA)]
        vias = [self.items[n] for n in route if isinstance(self.items[n], k.PCB_VIA)]
        widths = sorted({round(k.ToMM(t.GetWidth()), 6) for t in tracks})
        resistance = sum(self.weights[n] for n in route)
        return {"start": start, "end": end, "found_without_zones": True, "route_segment_length_mm": round(sum(k.ToMM(t.GetLength()) for t in tracks), 6), "widths_mm": widths, "via_drills_mm": [k.ToMM(v.GetDrill()) for v in vias], "assumed_current_A": current_A, "one_route_R20_mohm": resistance * 1000, "one_route_drop20_mV": resistance * current_A * 1000, "one_route_copper_loss20_mW": current_A ** 2 * resistance * 1000, "track_UUIDs": [uid(t) for t in tracks], "via_UUIDs": [uid(v) for v in vias], "pads_traversed": [self.labels[n] for n in route if n in self.labels]}


def main():
    inputs, boards = {}, {}
    for name in ["POWER", "LOGIC"]:
        project = "MeshRepeater2_" + name.title()
        folder = ROOT / "design" / project
        ppath = folder / (project + ".kicad_pcb")
        mpath = folder / "model.json"
        for path in [ppath, mpath]:
            inputs[path] = sha(path)
        model = json.loads(mpath.read_text(encoding="utf-8"))
        b = k.LoadBoard(str(ppath))
        graph = TraceGraph(b)
        footprints = {f.GetReference(): f for f in b.GetFootprints()}
        code_to_logical = {}
        for part in model["parts"]:
            for pad in footprints[part["ref"]].Pads():
                logical = part["nets"].get(pad.GetNumber())
                if logical is not None:
                    code_to_logical[pad.GetNetCode()] = logical
        track_summary, via_summary = defaultdict(list), defaultdict(list)
        for t in b.GetTracks():
            logical = code_to_logical.get(t.GetNetCode(), t.GetNetname())
            if isinstance(t, k.PCB_VIA):
                via_summary[logical].append({"at": mm(t.GetPosition()), "drill_mm": k.ToMM(t.GetDrill()), "diameter_F_Cu_mm": k.ToMM(t.GetWidth(k.F_Cu)), "diameter_B_Cu_mm": k.ToMM(t.GetWidth(k.B_Cu))})
            else:
                track_summary[logical].append({"uuid": uid(t), "width_mm": k.ToMM(t.GetWidth()), "length_mm": k.ToMM(t.GetLength()), "layer": b.GetLayerName(t.GetLayer()), "start": mm(t.GetStart()), "end": mm(t.GetEnd())})
        summaries = {}
        for net in ["SOLAR", "BAT", "SYS_PRE", "SYS_LC_IN", "FILTER_MID", "FILTER_OUT", "SYS_3V3", "RADIO_3V3", "BAT_ADC", "ANT_RF", "ANT_SMA", "LX1", "LX2", "SW_CHG"]:
            if net not in track_summary:
                continue
            ts = track_summary[net]
            widths = sorted({t["width_mm"] for t in ts})
            summaries[net] = {"tracks": ts, "total_drawn_segment_length_mm": sum(t["length_mm"] for t in ts), "length_by_width_mm": {str(w): sum(t["length_mm"] for t in ts if t["width_mm"] == w) for w in widths}, "vias": via_summary[net]}
        connector = "J101" if name == "POWER" else "J201"
        ground_contacts = []
        for number in [2, 4, 6, 8, 10, 12]:
            pad = next(p for p in footprints[connector].Pads() if p.GetNumber() == str(number))
            linked = b.GetConnectivity().GetConnectedItems(pad)
            ground_contacts.append({"pin": number, "net": pad.GetNetname(), "connected_items": len(linked), "ground_zones_in_native_connected_group": len({uid(z) for z in linked if isinstance(z, k.ZONE) and not z.GetIsRuleArea() and z.GetNetname() == "GND"}), "working_return_not_dependent_on_external_standoff": any(isinstance(z, k.ZONE) and z.GetNetname() == "GND" for z in linked)})
        board_result = {"dimensions_model_mm": [model["board"]["width"], model["board"]["height"]], "thickness_native_mm": k.ToMM(b.GetDesignSettings().GetBoardThickness()), "copper_layers": b.GetCopperLayerCount(), "design_copper_um": model["board"].get("copper_thickness_um"), "native_unconnected_count": b.GetConnectivity().GetUnconnectedCount(False), "connector_ground_contacts": ground_contacts, "nets": summaries, "paths": {}, "model_current_envelope": model.get("current_budget")}
        if name == "POWER":
            pairs = {"solar_to_bulk": (["J7", "1"], ["C8", "1"], 0.8), "solar_bulk_to_switch": (["C8", "1"], ["Q1", "2"], 0.8), "battery_to_TPS": (["J8", "1"], ["U2", "10"], 1.25), "battery_to_C53": (["J8", "1"], ["C53", "1"], 1.25), "C53_to_TPS": (["C53", "1"], ["U2", "10"], 1.25), "battery_to_sense_cable": (["J8", "1"], ["J101", "9"], 1.25e-6), "TPS_to_C12": (["U2", "10"], ["C12", "1"], 1.25), "TPS_to_C14": (["U2", "6"], ["C14", "1"], 0.5), "TPS_to_R55": (["U2", "6"], ["R55", "1"], 0.5), "R55_to_L3": (["R55", "2"], ["L3", "1"], 0.5), "L3_to_L4": (["L3", "2"], ["L4", "1"], 0.5)}
            for pin in [1, 3, 5, 7]:
                pairs["L4_to_cable_" + str(pin)] = (["L4", "2"], ["J101", str(pin)], 0.5)
        else:
            pairs = {"J11_to_MCU": (["J11", "2"], ["M1", "9"], 0.5), "J11_to_FB1": (["J11", "2"], ["FB1", "1"], 0.5), "J11_to_C21": (["J11", "2"], ["C21", "1"], 0.5), "FB1_to_modem": (["FB1", "2"], ["M2", "3"], 0.5), "modem_to_C23": (["M2", "3"], ["C23", "1"], 0.5), "modem_to_C24": (["M2", "3"], ["C24", "1"], 0.5), "battery_sense_to_divider": (["J201", "9"], ["R27", "1"], 1.25e-6), "ADC_to_MCU": (["R27", "2"], ["M1", "8"], 0), "SMA_trace": (["J13", "1"], ["FL1", "5"], 0), "RF_input_trace": (["M2", "1"], ["FL1", "2"], 0)}
            for pin in [1, 3, 5, 7]:
                pairs["cable_" + str(pin) + "_to_J11"] = (["J201", str(pin)], ["J11", "1"], 0.5)
        for title, (start, end, current) in pairs.items():
            board_result["paths"][title] = graph.path(start, end, current)
        if name == "POWER":
            main = board_result["paths"]["battery_to_TPS"]
            sense = board_result["paths"]["battery_to_sense_cable"]
            board_result["battery_sense_shared_native_track_UUIDs"] = sorted(set(main.get("track_UUIDs", [])) & set(sense.get("track_UUIDs", [])))
            board_result["battery_sense_route_excluding_selected_main_tracks"] = graph.path(["J8", "1"], ["J101", "9"], 1.25e-6, main.get("track_UUIDs", []))
        else:
            mcu = board_result["paths"]["J11_to_MCU"]
            modem = board_result["paths"]["J11_to_FB1"]
            shared = set(mcu.get("track_UUIDs", [])) & set(modem.get("track_UUIDs", []))
            board_result["MCU_modem_common_SYS_feed"] = {"track_UUIDs": sorted(shared), "shared_drawn_length_mm": sum(k.ToMM(graph.items[u].GetLength()) for u in shared), "shared_trace_R20_mohm": sum(graph.weights[u] for u in shared) * 1000, "scope": "Overlap of two shortest full-segment routes. Shared cable/J11 and GND impedance are additional; no claim of load isolation."}
            keepouts = []
            for zone in b.Zones():
                if not zone.GetIsRuleArea():
                    continue
                outline = zone.Outline()
                overlaps = []
                for copper_zone in b.Zones():
                    if copper_zone.GetIsRuleArea():
                        continue
                    for layer in [k.F_Cu, k.B_Cu]:
                        if copper_zone.HasFilledPolysForLayer(layer):
                            area = intersection_area(outline, copper_zone.GetFilledPolysList(layer))
                            if area > 1e-9:
                                overlaps.append({"net": copper_zone.GetNetname(), "layer": b.GetLayerName(layer), "area_mm2": area})
                keepouts.append({"outline": [mm(outline.CVertex(i)) for i in range(outline.TotalVertices())], "layer_set": zone.GetLayerSet().FmtHex(), "forbid_tracks": zone.GetDoNotAllowTracks(), "forbid_vias": zone.GetDoNotAllowVias(), "forbid_pads": zone.GetDoNotAllowPads(), "forbid_zone_fills": zone.GetDoNotAllowZoneFills(), "filled_zone_overlap": overlaps})
            board_result["BLE_native_rule_areas"] = keepouts
            rf_samples = []
            gnd_polys = [z.GetFilledPolysList(k.F_Cu) for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND" and z.HasFilledPolysForLayer(k.F_Cu)]
            for net in ["ANT_RF", "ANT_SMA"]:
                for track in track_summary[net]:
                    if track["layer"] != "F.Cu":
                        continue
                    a, c = track["start"], track["end"]
                    count = max(1, math.ceil(track["length_mm"] / 0.05))
                    gap = math.inf
                    at_min = None
                    for n in range(count + 1):
                        pos = k.VECTOR2I(k.FromMM(a[0] + (c[0] - a[0]) * n / count), k.FromMM(a[1] + (c[1] - a[1]) * n / count))
                        if gnd_polys:
                            candidate = min(k.ToMM(p.Distance(pos)) for p in gnd_polys) - track["width_mm"] / 2
                            if candidate < gap:
                                gap, at_min = candidate, mm(pos)
                    rf_samples.append({"track_uuid": track["uuid"], "net": net, "width_mm": track["width_mm"], "sampled_min_F_zone_edge_gap_mm": gap if math.isfinite(gap) else None, "sampled_track_center_at_min_mm": at_min, "sampling_step_max_mm": 0.05, "ground_scope": "FilledF.CuGNDzone, not a component ground pad"})
            board_result["RF_to_F_GND_zone_gap_samples"] = rf_samples
        boards[name] = board_result
    selection_path = ROOT / "docs" / "mechanical_selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    inputs[selection_path] = sha(selection_path)
    changed = [str(p.relative_to(ROOT)) for p in inputs if sha(p) != inputs[p]]
    out = {"stage": "INDEPENDENT_READ_ONLY_ROUTING_ENGINEERING_SNAPSHOT", "snapshot_stable": not changed, "changed_inputs": changed, "CAD_modified": False, "thermal_or_EMI_tests_performed": False, "method": "Native tracks/pads/vias and direct local connectivity. One complete-segment shortest resistive route excludes plane conduction; it is an engineering estimate, not a full parallel-network resistance solve. Native unconnected count is separate. No IPC2152 temperature/ampacity claim.", "assumptions": {"copper_rho20_ohm_m": RHO20, "finished_copper_um": 35, "minimum_via_plating_um": 20, "resistance_temperature_multiplier_at60C": 1 + 0.00393 * 40, "connector_continuous_design_A": 0.5, "BAT_input_design_A": 1.25, "SOLAR_path_test_envelope_A": 0.8, "wire_length_provisional_m": 0.12}, "boards": boards, "cable": selection["interboard"], "stack": selection.get("stack"), "sources": {"TPS_layout": "https://www.ti.com/lit/ds/symlink/tps63802.pdf#page=28", "IDC_header": "https://en.connfly.com/static/upload/file/pdf/DS1013.pdf", "IDC_socket": "docs/mechanical_sources/DS1016.pdf", "socket_catalogue_rating": "1A from previously checked Dan article195394; DS1016 manufacturer drawing does not state ampacity", "cable": "docs/mechanical_sources/DS1057.pdf"}, "inputs": {str(p.relative_to(ROOT)): digest for p, digest in inputs.items()}}
    destination = ROOT / "audit" / "v2_routing_engineering.json"
    destination.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    concise = {name: {"unconnected": d["native_unconnected_count"], "paths": {n: {field: p.get(field) for field in ["found_without_zones", "route_segment_length_mm", "widths_mm", "one_route_R20_mohm", "one_route_drop20_mV"]} for n, p in d["paths"].items()}, "common_SYS": d.get("MCU_modem_common_SYS_feed"), "BATsense_shared": d.get("battery_sense_shared_native_track_UUIDs"), "BLE_overlap": [x["filled_zone_overlap"] for x in d.get("BLE_native_rule_areas", [])], "RF_gap_min": min((x["sampled_min_F_zone_edge_gap_mm"] for x in d.get("RF_to_F_GND_zone_gap_samples", []) if x["sampled_min_F_zone_edge_gap_mm"] is not None), default=None)} for name, d in boards.items()}
    print(json.dumps({"stable": not changed, "summary": concise, "report": str(destination.relative_to(ROOT))}, ensure_ascii=True))


if __name__ == "__main__":
    main()
