"""Narrow, immutable-baseline allowance for the authorized INA219 addition.

This is not a replacement baseline. The stored PCB/model/XML nets must keep
BAT and BAT_SYS separate; only a separate legacy graph projection joins R71.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
FEATURE_PATH = ROOT / "design" / "feature_ina219_vertical.json"
BASELINE_SHA256 = "478b416c5fa28fbe4cebbc594eb1b519e90cb6c393aba6f58130b6fecffdac08"
INA_SOIC_PIN_NAMES = {"1": "A1", "2": "A0", "3": "SDA", "4": "SCL", "5": "VS", "6": "GND", "7": "IN-", "8": "IN+"}
PINMAP = {"1": "FILTER_OUT", "2": "GND", "3": "FILTER_OUT", "4": "GND", "5": "FILTER_OUT", "6": "GND", "7": "SYS_3V3", "8": "GND", "9": "BAT", "10": "SDA", "11": "MODE", "12": "SCL"}
OVERRIDES = {"POWER": {"U1": {"14": "BAT_SYS"}, "R1": {"2": "BAT_SYS"}, "C4": {"1": "BAT_SYS"}, "R3": {"1": "BAT_SYS"}, "U2": {"10": "BAT_SYS"}, "C12": {"1": "BAT_SYS"}, "C13": {"1": "BAT_SYS"}, "C52": {"1": "BAT_SYS"}, "C53": {"1": "BAT_SYS"}, "C30": {"1": "BAT_SYS"}}}
NEW_NETS = {
    "U12": {"1": "GND", "2": "GND", "3": "SDA", "4": "SCL", "5": "SYS_3V3", "6": "GND", "7": "INA_VIN_M", "8": "INA_VIN_P"},
    "R71": {"1": "BAT_SYS", "2": "BAT"},
    "R72": {"1": "BAT_SYS", "2": "INA_VIN_P"},
    "R73": {"1": "BAT", "2": "INA_VIN_M"},
    "C63": {"1": "SYS_3V3", "2": "GND"},
    "C64": {"1": "INA_VIN_P", "2": "INA_VIN_M"},
}
NEW_FIELDS = {
    "U12": ("INA219AIDR", "INA219AIDR", "INA219", "Meshcore:SOIC-8_3.9x4.9mm_P1.27mm"),
    "R71": ("0.1R 1% 1W", "RL2512FK-070R1L", "R", "Meshcore:R_2512_6332Metric"),
    "R72": ("10R 1%", "RC0805FR-0710RL", "R", "Meshcore:R_0805_2012Metric"),
    "R73": ("10R 1%", "RC0805FR-0710RL", "R", "Meshcore:R_0805_2012Metric"),
    "C63": ("100nF 50V X7R", "CC0805KRX7R9BB104", "C", "Meshcore:C_0805_2012Metric"),
    "C64": ("100nF 50V X7R", "CC0805KRX7R9BB104", "C", "Meshcore:C_0805_2012Metric"),
}
RAW_ENDPOINTS = {("J8", "1"), ("J12", "1"), ("R47", "1"), ("R15", "1"), ("TP1", "1"), ("J101", "9")}
LOWER_SYS_ENDPOINTS = {("J101", "7"), ("U12", "5"), ("C63", "1")}


def load_feature(contract_path):
    """Return the allowance only after proving its exact immutable source."""
    if not FEATURE_PATH.exists():
        return None
    contract_path = Path(contract_path).resolve()
    if contract_path != ROOT / "design" / "v2_electrical_contract.json":
        raise ValueError("INA219 authorization applies only to the frozen V2 contract")
    digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if digest != BASELINE_SHA256:
        raise ValueError("Frozen S4.16 electrical contract was modified")
    feature = json.loads(FEATURE_PATH.read_text(encoding="utf-8"))
    expected = {
        "baseline_contract_sha256": BASELINE_SHA256,
        "baseline_contract_immutable": True,
        "interboard_pinmap": PINMAP,
        "original_net_overrides": OVERRIDES,
        "INA219_expected_nets": NEW_NETS["U12"],
        "INA219_address": 0x40,
        "shunt_ohm": 0.1,
        "current_direction": "positive charge; negative discharge",
    }
    for key, value in expected.items():
        if feature.get(key) != value:
            raise ValueError("Unexpected INA219 allowance: " + key)
    if set(feature.get("new_references", [])) != set(NEW_NETS) or len(feature.get("new_references", [])) != len(NEW_NETS):
        raise ValueError("Only the six declared INA219 positions may be added")
    projection = feature.get("series_projection", {})
    if {key: projection.get(key) for key in ("reference", "pins", "nets")} != {"reference": "R71", "pins": ["1", "2"], "nets": ["BAT_SYS", "BAT"]}:
        raise ValueError("Only R71 can be collapsed for the legacy projection")
    raw = feature.get("raw_battery_endpoints", [])
    if len(raw) != len(RAW_ENDPOINTS) or {tuple(x) for x in raw} != RAW_ENDPOINTS:
        raise ValueError("Raw-battery endpoint allowance changed")
    return feature


def expected_original_nets(board, ref, original_nets, feature):
    expected = dict(original_nets)
    if feature:
        for pin, net in OVERRIDES.get(board, {}).get(ref, {}).items():
            if expected.get(pin) != "BAT":
                raise ValueError("BAT_SYS override must start from an original BAT pin")
            expected[pin] = net
    return expected


def feature_checks(models, feature):
    """Strict new circuit/variant checks, independent of model-generated graphs."""
    if not feature:
        return []
    parts = {board: {p["ref"]: p for p in model["parts"]} for board, model in models.items()}
    checks = []

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    check("INA219 six new positions remain only on POWER", all(ref in parts["POWER"] and ref not in parts["LOGIC"] for ref in NEW_NETS))
    for ref, nets in NEW_NETS.items():
        part = parts["POWER"].get(ref, {})
        check("INA219 exact circuit nets " + ref, part.get("nets") == nets, {"expected": nets, "actual": part.get("nets")})
        value, mpn, kind, footprint = NEW_FIELDS[ref]
        physical = part.get("source_footprint_before_v2_graphic_variant", part.get("footprint"))
        check("INA219 exact value/MPN/package and all variant fits " + ref,
              part.get("value") == value and part.get("mpn") == mpn and part.get("kind") == kind and physical == footprint
              and all(part.get(key) is True for key in ("fit_naion", "fit_naion_no_cold", "fit_lto2s"))
              and all(part.get(key, value) == value for key in ("value_naion_no_cold", "value_lto2s"))
              and all(part.get(key, mpn) == mpn for key in ("mpn_naion_no_cold", "mpn_lto2s"))
              and part.get("dnp", False) is False, {"physical_footprint": physical, "expected_footprint": footprint})
    for board, ref in (("POWER", "J101"), ("LOGIC", "J201")):
        check(board + " exact new twelve-pin interconnect nets", parts[board].get(ref, {}).get("nets") == PINMAP)
    power = parts["POWER"]
    raw = all(power.get(ref, {}).get("nets", {}).get(pin) == "BAT" for ref, pin in RAW_ENDPOINTS)
    check("Raw pack endpoints retain BAT before measurement shunt", raw)
    lower_sys = {(p["ref"], str(pin)) for p in power.values() for pin, net in p["nets"].items() if net == "SYS_3V3"}
    check("Returned SYS_3V3 powers only INA219 VS and its bypass on POWER", lower_sys == LOWER_SYS_ENDPOINTS, sorted(lower_sys))
    check("INA219 address straps fix 7-bit address 0x40", power.get("U12", {}).get("nets", {}).get("1") == "GND" and power.get("U12", {}).get("nets", {}).get("2") == "GND")
    check("J11 removable bridge remains FILTER_OUT to SYS_3V3", parts["LOGIC"].get("J11", {}).get("nets") == {"1": "FILTER_OUT", "2": "SYS_3V3"})
    check("FakeTec INA219 uses existing M1 I2C pads15/16", parts["LOGIC"].get("M1", {}).get("nets", {}).get("15") == "SDA" and parts["LOGIC"].get("M1", {}).get("nets", {}).get("16") == "SCL")
    return checks


def feature_native_checks(native_pin_net, feature):
    """Check actual native group separation before any legacy projection."""
    if not feature:
        return []
    checks = []

    def group(ref, pin):
        return native_pin_net.get(("POWER", ref, pin))

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    raw, system = group("R71", "2"), group("R71", "1")
    check("Native R71 keeps raw BAT and BAT_SYS distinct without bypass", raw is not None and system is not None and raw != system)
    check("Native raw-battery endpoints stay on shunt BAT side", raw is not None and all(group(ref, pin) == raw for ref, pin in RAW_ENDPOINTS))
    check("Native Kelvin pickup follows proper shunt sides", system is not None and group("R72", "1") == system and raw is not None and group("R73", "1") == raw)
    positive, negative = group("U12", "8"), group("U12", "7")
    check("Native INA differential RC filter endpoints", positive is not None and negative is not None and len({positive, negative, raw, system}) == 4 and group("R72", "2") == positive and group("C64", "1") == positive and group("R73", "2") == negative and group("C64", "2") == negative)
    vs, filtered = group("J101", "7"), group("J101", "1")
    check("Native INA VS return is separate from lower converter FILTER_OUT", vs is not None and filtered is not None and vs != filtered and all(group(ref, pin) == vs for ref, pin in LOWER_SYS_ENDPOINTS))
    return checks


def clone_union(union):
    """Copy group identity so legacy projection cannot mutate the physical proof."""
    projected = type(union)()
    projected.parents = dict(union.parents)
    return projected


def legacy_union(union, native_pin_net, feature):
    projected = clone_union(union)
    if feature:
        a = native_pin_net.get(("POWER", "R71", "1"))
        b = native_pin_net.get(("POWER", "R71", "2"))
        if a is None or b is None or a == b:
            raise ValueError("Native distinct R71 ends required before legacy projection")
        projected.join(a, b)
    return projected
