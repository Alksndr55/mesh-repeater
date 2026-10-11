"""Independent, read-only nominal geometry review of frame/mount alternatives."""
from pathlib import Path
import hashlib
import json
import math
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "design" / "MeshRepeater2_Power" / "MeshRepeater2_Power.kicad_pcb"
BASELINE_PCB = ROOT / "baseline" / "S4_16" / "Meshcore_NaIon.kicad_pcb"
KLC_URL = "https://klc.kicad.org/footprint/f5/f5.3/"


def rects_poly(rects):
    poly = k.SHAPE_POLY_SET()
    for x1, y1, x2, y2 in rects:
        poly.NewOutline()
        for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
            poly.Append(k.FromMM(x), k.FromMM(y))
    return poly


def intersection_area(a, b):
    result = k.SHAPE_POLY_SET()
    result.BooleanIntersection(a, b)
    return result.Area() / 1e12


def point_rect_distance(cx, cy, x1, y1, x2, y2):
    dx = max(x1 - cx, 0, cx - x2)
    dy = max(y1 - cy, 0, cy - y2)
    return math.hypot(dx, dy)


def main():
    source_hash = hashlib.sha256(PCB.read_bytes()).hexdigest()
    b = k.LoadBoard(str(PCB))
    footprints = {f.GetReference(): f for f in b.GetFootprints()}
    frame = footprints.get("SH1")
    frame_present_in_current_pcb = frame is not None
    frame_source = PCB
    if frame is None:
        baseline_board = k.LoadBoard(str(BASELINE_PCB))
        frame = next(f for f in baseline_board.GetFootprints() if f.GetReference() == "SH1")
        frame_source = BASELINE_PCB
    pads = [{"pin": p.GetNumber(), "x": k.ToMM(p.GetPosition().x), "y": k.ToMM(p.GetPosition().y), "size_x": k.ToMM(p.GetSize().x), "size_y": k.ToMM(p.GetSize().y), "net": p.GetNetname()} for p in frame.Pads()]
    frame_y = k.ToMM(frame.GetPosition().y)
    holes = [(3.5, 3.5), (86.5, 3.5), (3.5, 56.5), (86.5, 56.5)]
    # B preserves the original four closed courtyard-band method and .8 mm
    # offset. Unlike the rejected wall-only shape, it includes all solderlands.
    b_bands = [(7.2, 12.2, 82.8, 13.8), (7.2, 13.85, 8.8, 55.15),
               (7.2, 55.2, 82.8, 56.8), (81.2, 13.85, 82.8, 55.15)]
    b_court = rects_poly(b_bands)
    conflicts = []
    for ref, footprint in footprints.items():
        if ref == "SH1" or ref.startswith("H"):
            continue
        native = footprint.GetCourtyard(k.F_Cu)
        if native.OutlineCount():
            area = intersection_area(native, b_court)
            if area > 1e-8:
                conflicts.append({"reference": ref, "intersection_mm2": area})
    source_unchanged = hashlib.sha256(PCB.read_bytes()).hexdigest() == source_hash
    result = {
        "project": "Mesh Repeater2.0",
        "date": "2026-10-11",
        "review_scope": "Independent nominal mechanical and courtyard-definition review; no PCB or library mutations; not a final DRC or bench qualification",
        "inputs": {"pcb": str(PCB.relative_to(ROOT)).replace("\\", "/"), "sha256_at_read": source_hash, "file_unchanged_during_review": source_unchanged, "SH1_geometry_source": str(frame_source.relative_to(ROOT)).replace("\\", "/")},
        "native_snapshot": {"SH1_present_in_current_PCB": frame_present_in_current_pcb, "SH1_position_in_geometry_source": [k.ToMM(frame.GetPosition().x), frame_y], "SH1_pads_in_geometry_source": pads, "SH1_native_courtyard_offset_nominal_mm": 0.8, "ground_land_OD_mm": 6, "mounting_centres": holes},
        "normative_reference": {"url": KLC_URL, "retrieved": "2026-10-11", "interpretation": "A footprint courtyard accounts for both physical body and land pattern, with normally0.25mm clearance. A contoured polygon is allowed. Removing pad coverage or simply omitting modeled hardware does not establish conformity."},
        "rejected_wall_only_court": {
            "frame_offset_mm": 0.35, "wall_half_width_mm": 0.1,
            "actual_land_half_width_mm": 0.5,
            "pad_extension_beyond_wall_only_court_mm": 0.15,
            "required_pad_aware_half_offset_with_0_25_margin_mm": 0.75,
            "proposed_mount_margin_mm": 0.1,
            "nominal_wall_and_hardware_bodies_fit": True,
            "KLC_courtyard_conformity": False,
            "reason": "The wall-only courtyard omits0.15mm of each real solderland, even before adding courtyard clearance.0.1mm mounting reserve is not the normal0.25mm KLC clearance. No checks should be disabled to conceal this.",
        },
        "nominal_body_clearance_original_76x43_at_45_34_5": {
            "wall_outer_bounds": [6.9, 12.9, 83.1, 56.1],
            "lower_left_6mm_washer_to_frame_min_mm": point_rect_distance(3.5, 56.5, 6.9, 12.9, 83.1, 56.1) - 3,
            "lower_right_6mm_washer_to_frame_min_mm": point_rect_distance(86.5, 56.5, 6.9, 12.9, 83.1, 56.1) - 3,
            "aligned_hex_flat_to_vertical_wall_min_mm": 6.9 - (3.5 + 2.75),
            "hex_vertex_radius_mm": 5.5 / math.sqrt(3),
            "washer_plus_aligned_hex_profile_max_y_with0_25_margin_mm": 5.5 / math.sqrt(3) + 0.25,
            "existing_circle_R3_25_margin_at_hex_vertex_mm": 3.25 - 5.5 / math.sqrt(3),
            "conditional": "Nominal fit only; actual washer, hex orientation, frame width/tolerance and solder fillet need qualification. A full0.25mm buffered hardware profile is slightly taller than the existingR3.25circle.",
        },
        "alternative_A_hardware_external_to_contact_footprint": {
            "assessment": "Not independently accepted as a route to zero DRC. A PCB contact can be a board feature, but all actual spacers/washers must still be represented by honest assembly/courtyard/keepout geometry. Removing the only hardware boundary would hide the conflict rather than resolve it.",
            "conditional_acceptance": "Only with an explicit composite assembly footprint or equivalent complete geometry review that preserves the hardware/body/land coverage; no disabled courtyard checks and no claim that an omitted body was checked.",
        },
        "alternative_B_74x43_new_custom_frame": {
            "assessment": "Mechanically feasible with documented new custom frame and local rerouting; not a drop-in substitution for76x43.",
            "centre": [45, 34.5], "wall_centerlines": [8, 13, 82, 56], "wall_outer_bounds": [7.9, 12.9, 82.1, 56.1],
            "courtyard_bands": b_bands,
            "mount_to_frame_courtyard_horizontal_gap_mm": 7.2 - (3.5 + 3.25),
            "lower_left_washer_to_frame_min_mm": point_rect_distance(3.5, 56.5, 7.9, 12.9, 82.1, 56.1) - 3,
            "actual_native_component_courtyard_intersections": sorted(conflicts, key=lambda x: x["reference"]),
            "minimum_displacement_guidance": {"C8_R7_R8_R9": "Shift inward right by about0.5mm, then reroute and recheck", "C43_C45_C47_C49_C51": "Shift left by about0.85mm, then reroute and recheck", "J101": "Top strip courtyard must clear correctedframey13; nominal existing pad-aware court still intersects in this snapshot"},
            "requirements": ["Revise custom frame procurement/drawing/STEP/footprint to74x43; cannot order former76x43 frame", "Keep fourGND solderland electrical functions; mechanical pad resizing/movement and rerouting documented", "Update schematic/model/BOM and verify native final DRC; new pad locations may contact non-GND tracks", "Do not claim measured EMI equivalence"],
        },
        "alternative_C_explicit_removal_of_SH1": {
            "assessment": "Recommended if a new custom frame is unnecessary: explicit mechanical removal while retaining the grounded continuous intermediate90x60screen and full cableGND.",
            "benefits": ["No frame/mount courtyard conflict", "Avoids custom74x43part and unnecessary movement of charger/LC parts", "Existing working power and return do not rely on the frame", "The prompt allows an explicit frame decision; removal is not implied merely by removing old lid"],
            "constraints": ["Record removedSH1 as mechanical reference mapping; do not silently omit it", "Remove old frame footprint/model/BOM/drawing/instructions consistently", "Keep COLD/balancer grouping and surface markings", "Preserve continuous intermediate screen and electricalGND standoff contacts", "Loss of vertical sidewalls changes field confinement; EMI/thermal behavior remains unqualified and cannot be claimed equivalent"],
        },
        "verdict": "Wall-only courtyard rejected. Prefer explicitSH1removal if no mechanical need for sidewallframe; otherwise use documented74x43customframe and reposition/reroute the listed parts. Keep all DRC checks active.",
        "accepted_decision": {"choice": "C", "SH1": "removed", "authorized_by": "Parent accepted independent review on2026-10-11 within the prompt's explicit frame-decision scope", "rationale": "Retain continuous grounded intermediate screen and full cableGND without hiding any physical geometry or reducing courtyard coverage. No new custom frame, no additional component displacement, no claim of measured EMI equivalence.", "standoffs": "18mm lower and15mm upper retained; nominal inner spaces18.5mm and16mm per mechanical selection. Lower THERM12.5mm leaves6.0mm nominal vertical reserve."},
        "PCB_or_library_modified": False,
    }
    destination = ROOT / "audit" / "v2_frame_mount_review.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot_stable": source_unchanged, "SH1_y": frame_y, "B_conflicts": [r["reference"] for r in conflicts], "report": str(destination.relative_to(ROOT)), "verdict": result["verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
