"""Export a portable, checked GenCAD boardview from an unchanged native PCB.

KiCad 10's GenCAD export can alias copper pads to empty or incorrect padstacks.
Repair those stacks from pcbnew, remove non-copper apertures, expose native
values as DEVICE text, and use THOU for NexusBV's GenCAD importer.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


class BoardviewError(ValueError):
    """Export or verification failed; an existing destination is preserved."""


def _require(ok, message):
    if not ok:
        raise BoardviewError(message)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _quote(value):
    _require(not any(ord(c) < 32 for c in value), 'GenCAD text contains a control character')
    return json.dumps(value, ensure_ascii=False)


def _sections(text):
    result = defaultdict(list)
    section = None
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith('$END'):
            section = None
        elif line.startswith('$'):
            section = line[1:]
        elif section and line.strip():
            result[section].append((number, shlex.split(line)))
    return result


def _parse(text):
    sections = _sections(text)
    units = [t[1] for _, t in sections['HEADER'] if t[0] == 'UNITS']
    _require(len(units) == 1 and units[0] in ('INCH', 'THOU'), 'Unsupported GenCAD units')
    data = {'sections': sections, 'units': units[0], 'scale': {'INCH': 25.4, 'THOU': .0254}[units[0]],
            'stacks': {}, 'pads': {}, 'shapes': {}, 'components': {}, 'nodes': []}
    for _, t in sections['PADSTACKS']:
        if t[0] == 'PADSTACK':
            current = {'drill': float(t[2]), 'pads': []}
            data['stacks'][t[1]] = current
        elif t[0] == 'PAD':
            current['pads'].append((t[1], t[2]))
    for _, t in sections['PADS']:
        if t[0] == 'PAD':
            current = []
            data['pads'][t[1]] = current
        else:
            current.append(t)
    for _, t in sections['SHAPES']:
        if t[0] == 'SHAPE':
            current = []
            data['shapes'][t[1]] = current
        elif t[0] == 'PIN':
            current.append(t)
    for _, t in sections['COMPONENTS']:
        if t[0] == 'COMPONENT':
            _require(t[1] not in data['components'], 'Duplicate GenCAD component: ' + t[1])
            current = {}
            data['components'][t[1]] = current
        elif t[0] in ('PLACE', 'ROTATION', 'SHAPE', 'LAYER', 'DEVICE'):
            current[t[0]] = t[1:]
    for _, t in sections['SIGNALS']:
        if t[0] == 'SIGNAL':
            net = t[1]
        elif t[0] == 'NODE':
            data['nodes'].append((t[1], t[2], net))
    return data


def _world(component, pin, scale):
    px, py = map(float, component['PLACE'])
    x, y = map(float, pin[3:5])
    flags = component['SHAPE'][1:]
    mx, my = (-1 if 'MIRRORX' in flags else 1), (-1 if 'MIRRORY' in flags else 1)
    angle = math.radians(float(component['ROTATION'][0]))
    if mx * my == -1:
        angle = math.pi - angle
    co, si = math.cos(angle), math.sin(angle)
    return ((px + mx * (x * co - y * si)) * scale,
            -(py + my * (x * si + y * co)) * scale)


def _position(point, pcbnew):
    return (pcbnew.ToMM(point.x), pcbnew.ToMM(point.y))


def _sides(pad, pcbnew):
    return {name for layer, name in ((pcbnew.F_Cu, 'TOP'), (pcbnew.B_Cu, 'BOTTOM')) if pad.IsOnLayer(layer)}


def _match(remaining, pin, position, pcbnew, ref):
    for pad in remaining:
        if ((pad.GetNumber() or 'none') == pin[1]
                and math.dist(position, _position(pad.GetPosition(), pcbnew)) < 1e-5):
            remaining.remove(pad)
            return pad
    raise BoardviewError(f'Unmatched exported pad: {ref}.{pin[1]} at {position}')


def _geometry(pad, name, pcbnew):
    """Return physical pad primitives in native GenCAD inches."""
    w, h = (pcbnew.ToMM(v) / 25.4 for v in (pad.GetSize().x, pad.GetSize().y))
    drill = pcbnew.ToMM(pad.GetDrillSize().x) / 25.4
    num = lambda v: format(v, '.16g')
    shape = pad.GetShape()
    if shape == pcbnew.PAD_SHAPE_CIRCLE:
        return [f'PAD {name} ROUND {num(drill)}', f'CIRCLE 0 0 {num(w / 2)}']
    if shape == pcbnew.PAD_SHAPE_RECT:
        return [f'PAD {name} RECTANGULAR {num(drill)}',
                f'RECTANGLE {num(-w/2)} {num(-h/2)} {num(w)} {num(h)}']
    _require(shape in (pcbnew.PAD_SHAPE_ROUNDRECT, pcbnew.PAD_SHAPE_OVAL),
             f'Unsupported pad shape requiring GenCAD repair: {name} ({shape})')
    radius = pcbnew.ToMM(pad.GetRoundRectCornerRadius()) / 25.4 if shape == pcbnew.PAD_SHAPE_ROUNDRECT else min(w, h) / 2
    x, y = w / 2, h / 2
    points = [(-x+radius, -y), (x-radius, -y), (x, -y+radius), (x, y-radius),
              (x-radius, y), (-x+radius, y), (-x, y-radius), (-x, -y+radius)]
    centers = [(x-radius, -y+radius), (x-radius, y-radius), (-x+radius, y-radius), (-x+radius, -y+radius)]
    result = [f'PAD {name} POLYGON {num(drill)}']
    for k in range(4):
        a, z = points[2*k], points[2*k+1]
        if math.dist(a, z) > 1e-12:
            result.append('LINE ' + ' '.join(map(num, (*a, *z))))
        result.append('ARC ' + ' '.join(map(num, (*z, *points[(2*k+2) % 8], *centers[k]))))
    return result


def _assembly_metadata(native, assembly_variant, model_path):
    """Select assembly values/fit without removing any physical PCB objects."""
    variant = 'NaIon_COLD' if assembly_variant is None else assembly_variant
    suffixes = {'NaIon_COLD': 'naion', 'LTO_2S': 'lto2s'}
    _require(variant in suffixes, 'Unsupported boardview assembly variant: ' + str(variant))
    values = {ref: fp.GetValue() for ref, fp in native.items()}
    fitted = {ref: True for ref in native}
    report = {'assembly_variant': variant}
    if model_path is not None:
        model_path = Path(model_path)
        _require(model_path.is_file(), 'Missing boardview assembly model: ' + str(model_path))
        raw = model_path.read_bytes()
        model = json.loads(raw.decode('utf-8-sig'))
        _require(isinstance(model, dict), 'Invalid assembly model document')
        parts = model.get('parts')
        _require(isinstance(parts, list) and all(isinstance(part, dict) for part in parts), 'Invalid model parts list')
        references = [part.get('ref') for part in parts]
        _require(all(isinstance(ref, str) and ref for ref in references), 'Invalid model component reference')
        _require(len(set(references)) == len(references), 'Duplicate model component references')
        _require(set(references) == set(native), 'Assembly model/PCB reference set mismatch')
        suffix = suffixes[variant]
        for part in parts:
            ref = part['ref']
            _require('value' in part, 'Missing base model value: ' + ref)
            value = part.get('value_' + suffix, part['value'])
            dnp = part.get('dnp', False)
            fit = part.get('fit_' + suffix, not dnp)
            _require(isinstance(value, str) and bool(value.strip()), 'Invalid assembly value: ' + ref)
            _require(isinstance(dnp, bool) and isinstance(fit, bool), 'Invalid assembly fit flag: ' + ref)
            values[ref], fitted[ref] = value, fit
        report.update(model_sha256=hashlib.sha256(raw).hexdigest(), model_file=model_path.name)
    devices = {ref: value if fitted[ref] else 'DNP' if value.strip().upper() == 'DNP' else 'DNP | ' + value
               for ref, value in values.items()}
    report.update(component_values=dict(sorted(values.items())), component_fitted=dict(sorted(fitted.items())),
                  component_device_text=dict(sorted(devices.items())))
    return report


def _repair(text, native, pcbnew, device_values=None):
    parsed = _parse(text)
    _require(parsed['units'] == 'INCH', 'Expected INCH output from native KiCad GenCAD exporter')
    _require(set(parsed['components']) == set(native), 'Native/GenCAD component set differs')
    remaining = {ref: list(fp.Pads()) for ref, fp in native.items()}
    output, newpads, newstacks = [], [], []
    removed = corrected = 0
    section = ref = ''
    for line in text.splitlines():
        if line.startswith('$'):
            section = line
        t = shlex.split(line)
        if t and section == '$SHAPES':
            if t[0] == 'SHAPE':
                ref = t[1]
            elif t[0] == 'PIN':
                component = parsed['components'][ref]
                pad = _match(remaining[ref], t, _world(component, t, 25.4), pcbnew, ref)
                sides = _sides(pad, pcbnew)
                if not sides:
                    _require(pad.GetNetCode() == 0 and pad.GetDrillSize().x == 0 and pad.GetDrillSize().y == 0,
                             f'Cannot discard a connected/drilled non-copper pad: {ref}.{t[1]}')
                    removed += 1
                    continue
                stack = parsed['stacks'].get(t[2])
                stack_sides = {p[1] for p in stack['pads']} if stack else set()
                if 'FLIP' in component['SHAPE'][1:]:
                    stack_sides = {'BOTTOM' if s == 'TOP' else 'TOP' if s == 'BOTTOM' else s for s in stack_sides}
                needs_repair = stack_sides != sides
                if stack and stack['pads']:
                    try:
                        _validate_geometry(parsed, stack, pad, pcbnew, ref + '.' + t[1])
                    except BoardviewError:
                        needs_repair = True
                else:
                    needs_repair = True
                if needs_repair:
                    local_angle = pad.GetOrientationDegrees() - native[ref].GetOrientationDegrees()
                    _require(abs((local_angle + 90) % 180 - 90) < 1e-5,
                             f'Unsupported local pad rotation requiring GenCAD repair: {ref}.{t[1]}')
                    corrected += 1
                    padname, stackname = f'BV_PAD_{corrected}', f'BV_STACK_{corrected}'
                    _require(padname not in parsed['pads'] and stackname not in parsed['stacks'], 'Native GenCAD name collision')
                    newpads.extend(_geometry(pad, padname, pcbnew))
                    if 'FLIP' in component['SHAPE'][1:]:
                        sides = {'BOTTOM' if s == 'TOP' else 'TOP' for s in sides}
                    drill = pcbnew.ToMM(pad.GetDrillSize().x) / 25.4
                    newstacks.append(f'PADSTACK {stackname} {drill:.16g}')
                    newstacks.extend(f'PAD {padname} {s} 0 0' for s in sorted(sides))
                    t[2] = stackname
                    line = 'PIN ' + _quote(t[1]) + ' ' + ' '.join(t[2:])
        elif t and section == '$COMPONENTS':
            if t[0] == 'COMPONENT':
                ref = t[1]
            elif t[0] == 'DEVICE':
                line = 'DEVICE ' + _quote(device_values[ref] if device_values is not None else native[ref].GetValue())
        output.append(line)
    _require(not any(remaining.values()), 'Native pads missing from GenCAD export')
    result = '\n'.join(output) + '\n'
    if newpads:
        result = result.replace('$ENDPADS', '\n'.join(newpads) + '\n$ENDPADS', 1)
        result = result.replace('$ENDPADSTACKS', '\n'.join(newstacks) + '\n$ENDPADSTACKS', 1)
    return result, {'removed_non_copper_pads': removed, 'repaired_padstacks': corrected}


def _normalize_units(text):
    """Scale only dimensional fields; names, angles and metadata stay intact."""
    fields = {('HEADER', 'ORIGIN'): (1, 2), ('HEADER', 'INTERTRACK'): (1,),
              ('PADS', 'PAD'): (3,), ('PADSTACKS', 'PADSTACK'): (2,), ('PADSTACKS', 'PAD'): (3, 4),
              ('SHAPES', 'PIN'): (3, 4), ('COMPONENTS', 'PLACE'): (1, 2),
              ('COMPONENTS', 'TEXT'): (1, 2, 3, 8, 9, 10, 11),
              ('TRACKS', 'TRACK'): (2,), ('ROUTES', 'VIA'): (2, 3, 5)}
    geometry = {'LINE': 4, 'ARC': 6, 'CIRCLE': 3, 'RECTANGLE': 4}
    output, section, unit_count = [], '', 0
    for line in text.splitlines():
        if line.startswith('$'):
            section = line[1:]
        t = re.findall(r'"(?:[^"\\]|\\.)*"|\S+', line)
        if t:
            op = t[0]
            if op == 'UNITS':
                _require(t == ['UNITS', 'INCH'], 'Expected exactly UNITS INCH')
                t[1] = 'THOU'
                unit_count += 1
                line = ' '.join(t)
            indices = fields.get((section, op), ())
            if op in geometry:
                _require(len(t) == geometry[op] + 1, 'Unsupported GenCAD geometry record: ' + op)
                indices = range(1, len(t))
            if indices:
                for i in indices:
                    t[i] = format(Decimal(t[i]) * 1000, 'f')
                line = ' '.join(t)
        output.append(line)
    _require(unit_count == 1, 'Missing or repeated GenCAD UNITS')
    return '\n'.join(output) + '\n'


def _rounded(point):
    return tuple(round(v, 5) for v in point)


def _edge(a, z):
    return tuple(sorted((_rounded(a), _rounded(z))))


def _validate_geometry(parsed, stack, pad, pcbnew, label):
    scale = parsed['scale']
    drill = pad.GetDrillSize()
    _require(drill.x == drill.y, 'Slotted drill is not representable by this GenCAD export: ' + label)
    _require(abs(stack['drill'] * scale - pcbnew.ToMM(drill.x)) < 1e-5, 'Pad drill mismatch: ' + label)
    size = _position(pad.GetSize(), pcbnew)
    for primitive in {p[0] for p in stack['pads']}:
        _require(primitive in parsed['pads'], 'Unresolved pad primitive: ' + primitive)
        points, radii = [], []
        for t in parsed['pads'][primitive]:
            op = t[0]
            vals = [float(v) * scale for v in t[1:]]
            if op == 'LINE':
                points.extend((vals[:2], vals[2:4]))
            elif op == 'RECTANGLE':
                x, y, w, h = vals
                points.extend(((x, y), (x+w, y+h)))
            elif op == 'CIRCLE':
                x, y, r = vals
                points.extend(((x-r, y-r), (x+r, y+r)))
            elif op == 'ARC':
                x1, y1, x2, y2, cx, cy = vals
                points.extend(((x1, y1), (x2, y2)))
                radii.extend((math.hypot(x1-cx, y1-cy), math.hypot(x2-cx, y2-cy)))
            else:
                raise BoardviewError('Unsupported pad primitive: ' + op)
        _require(bool(points), 'Empty pad geometry: ' + label)
        xs, ys = zip(*points)
        bounds = (max(xs)-min(xs), max(ys)-min(ys))
        _require(max(abs(a-z) for a, z in zip(bounds, size)) < 1e-5, 'Pad dimensions mismatch: ' + label)
        _require(max(abs(max(xs)+min(xs)), abs(max(ys)+min(ys))) < 1e-5, 'Pad center offset mismatch: ' + label)
        if primitive.startswith('BV_PAD_') and pad.GetShape() in (pcbnew.PAD_SHAPE_ROUNDRECT, pcbnew.PAD_SHAPE_OVAL):
            radius = pcbnew.ToMM(pad.GetRoundRectCornerRadius()) if pad.GetShape() == pcbnew.PAD_SHAPE_ROUNDRECT else min(size)/2
            _require(len(radii) == 8 and all(abs(r-radius) < 1e-5 for r in radii), 'Pad arc radius mismatch: ' + label)


def _validate(text, board, native, pcbnew, device_values=None):
    parsed = _parse(text)
    _require(parsed['units'] == 'THOU', 'Boardview must use THOU')
    _require(set(parsed['components']) == set(native), 'Component reference set mismatch')
    nodes = Counter(parsed['nodes'])
    expected_nodes = Counter()
    nodes_by_pin = defaultdict(set)
    for ref, pin, net in nodes:
        nodes_by_pin[ref, pin].add(net)
    retained = drilled = 0
    duplicates = {}
    for ref, footprint in native.items():
        component = parsed['components'][ref]
        expected_value = device_values[ref] if device_values is not None else footprint.GetValue()
        _require(component['DEVICE'] == [expected_value], 'Component value mismatch: ' + ref)
        position = tuple(float(v) * parsed['scale'] * sign for v, sign in zip(component['PLACE'], (1, -1)))
        _require(math.dist(position, _position(footprint.GetPosition(), pcbnew)) < 1e-5, 'Component position mismatch: ' + ref)
        expected_side = 'BOTTOM' if footprint.GetLayer() == pcbnew.B_Cu else 'TOP'
        _require(component['LAYER'] == [expected_side], 'Component side mismatch: ' + ref)
        rotation = float(component['ROTATION'][0]) - footprint.GetOrientationDegrees()
        _require(abs((rotation + 180) % 360 - 180) < 1e-5, 'Component rotation mismatch: ' + ref)
        remaining = [p for p in footprint.Pads() if _sides(p, pcbnew)]
        duplicate = {pin: n for pin, n in Counter(p.GetNumber() for p in remaining).items() if n > 1}
        if duplicate:
            duplicates[ref] = duplicate
        for pin in parsed['shapes'][component['SHAPE'][0]]:
            pad = _match(remaining, pin, _world(component, pin, parsed['scale']), pcbnew, ref)
            retained += 1
            drilled += bool(pad.GetDrillSize().x)
            label = ref + '.' + pin[1]
            stack = parsed['stacks'].get(pin[2])
            _require(stack is not None and bool(stack['pads']), 'Missing/empty padstack: ' + label)
            sides = {p[1] for p in stack['pads']}
            if 'FLIP' in component['SHAPE'][1:]:
                sides = {'BOTTOM' if s == 'TOP' else 'TOP' if s == 'BOTTOM' else s for s in sides}
            _require(sides == _sides(pad, pcbnew), 'Pad copper side mismatch: ' + label)
            expected_net = {pad.GetNetname()} if pad.GetNetCode() else set()
            _require(nodes_by_pin[ref, pin[1]] == expected_net, 'Pad net mismatch: ' + label)
            if pad.GetNetCode():
                expected_nodes[ref, pin[1], pad.GetNetname()] += 1
            _validate_geometry(parsed, stack, pad, pcbnew, label)
        _require(not remaining, 'Copper/mechanical pads omitted: ' + ref)
    _require(nodes == expected_nodes, 'Signal node multiset mismatch')
    scale = parsed['scale']
    xy = lambda t: (float(t[0]) * scale, -float(t[1]) * scale)
    native_edges = Counter()
    # Native GenCAD tessellates the board polygon, including footprint cutouts.
    # Looking only at board.GetDrawings() would miss SHIELD's rounded HS1 hole.
    polygon = pcbnew.SHAPE_POLY_SET()
    _require(board.GetBoardPolygonOutlines(polygon, False), 'Cannot obtain native board outline')
    for outer in range(polygon.OutlineCount()):
        rings = [polygon.Outline(outer)] + [polygon.Hole(outer, h) for h in range(polygon.HoleCount(outer))]
        for ring in rings:
            for i in range(ring.PointCount()):
                native_edges[_edge(_position(ring.CPoint(i), pcbnew),
                                   _position(ring.CPoint((i+1) % ring.PointCount()), pcbnew))] += 1
    export_edges = Counter()
    for _, t in parsed['sections']['BOARD']:
        _require(t[0] == 'LINE', 'Unsupported GenCAD board outline primitive: ' + t[0])
        export_edges[_edge(xy(t[1:3]), xy(t[3:5]))] += 1
    _require(native_edges == export_edges, 'Board outline mismatch')
    native_tracks, native_vias = Counter(), Counter()
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            native_vias[(_rounded(_position(track.GetPosition(), pcbnew)), track.GetNetname(),
                         round(pcbnew.ToMM(track.GetDrillValue()), 5), round(pcbnew.ToMM(track.GetWidth(pcbnew.F_Cu)), 5))] += 1
        else:
            _require(not isinstance(track, pcbnew.PCB_ARC), 'Unsupported curved copper track in GenCAD validation')
            native_tracks[(_edge(_position(track.GetStart(), pcbnew), _position(track.GetEnd(), pcbnew)), track.GetNetname(),
                           board.GetLayerName(track.GetLayer()), round(pcbnew.ToMM(track.GetWidth()), 5))] += 1
    widths = {t[1]: round(float(t[2]) * scale, 5) for _, t in parsed['sections']['TRACKS'] if t[0] == 'TRACK'}
    export_tracks, export_vias = Counter(), Counter()
    width = layer = net = None
    for _, t in parsed['sections']['ROUTES']:
        if t[0] == 'ROUTE':
            net = t[1]
        elif t[0] == 'TRACK':
            width = widths.get(t[1])  # Via-only TRACK names need not have a $TRACKS definition.
        elif t[0] == 'LAYER':
            layer = {'TOP': 'F.Cu', 'BOTTOM': 'B.Cu'}.get(t[1], t[1])
        elif t[0] == 'LINE':
            _require(width is not None, 'Unresolved copper track width')
            export_tracks[(_edge(xy(t[1:3]), xy(t[3:5])), net, layer, width)] += 1
        elif t[0] == 'VIA':
            stack = parsed['stacks'][t[1]]
            primitive = parsed['pads'][stack['pads'][0][0]]
            _require(len(primitive) == 1 and primitive[0][0] == 'CIRCLE', 'Unsupported via pad geometry')
            diameter = float(primitive[0][3]) * scale * 2
            export_vias[(_rounded(xy(t[2:4])), net, round(float(t[5]) * scale, 5), round(diameter, 5))] += 1
        else:
            raise BoardviewError('Unsupported GenCAD route record: ' + t[0])
    _require(export_tracks == native_tracks, 'Copper track multiset mismatch')
    _require(export_vias == native_vias, 'Via multiset mismatch')
    return {'components': len(native), 'pads': retained, 'drilled_pads': drilled,
            'signal_nodes': sum(nodes.values()), 'nets': len({net for _, _, net in nodes}),
            'tracks': sum(native_tracks.values()), 'vias': sum(native_vias.values()),
            'outline_segments': sum(native_edges.values()), 'duplicate_pad_numbers': duplicates,
            'component_values': {ref: fp.GetValue() for ref, fp in sorted(native.items())}}


def _worker(pcb_path, cad_path, kicad_cli, *, assembly_variant=None, model_path=None):
    """Use KiCad's adjacent Python when the release interpreter lacks pcbnew."""
    executable = Path(shutil.which(str(kicad_cli)) or kicad_cli).resolve()
    python = executable.with_name('python.exe' if sys.platform == 'win32' else 'python3')
    _require(python.is_file() and python.resolve() != Path(sys.executable).resolve(),
             'pcbnew unavailable; run the release with KiCad Python or provide its kicad-cli path')
    with tempfile.TemporaryDirectory(prefix='boardview-report-') as folder:
        report_path = Path(folder) / 'report.json'
        options = {'assembly_variant': assembly_variant, 'model_path': str(model_path) if model_path is not None else None}
        command = [str(python), str(Path(__file__).resolve()), '--worker', str(pcb_path), str(cad_path),
                   str(executable), str(report_path), json.dumps(options)]
        proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        _require(proc.returncode == 0 and report_path.is_file(), 'Boardview worker failed: ' + (proc.stderr or proc.stdout)[-4000:])
        return json.loads(report_path.read_text('utf-8'))


def export_boardview(pcb_path: Path, cad_path: Path, kicad_cli: str | Path,
                     *, assembly_variant=None, model_path=None) -> dict:
    """Write validated GenCAD and return a JSON-safe audit; raise ValueError on failure.

    pcbnew is imported only here. If needed, KiCad's adjacent Python runs this
    same API in a worker. Existing CAD is replaced only after validation passes.
    Assembly defaults to NaIon_COLD; LTO_2S selects the corresponding model
    values/fit flags. Without a model, native common values are used. DNP parts
    retain their physical pads, nets and positions and receive DEVICE marking.
    """
    pcb_path, cad_path = Path(pcb_path).resolve(), Path(cad_path).resolve()
    _require(pcb_path.is_file(), 'Missing PCB: ' + str(pcb_path))
    _require(cad_path != pcb_path, 'Boardview destination must differ from the native PCB')
    assembly_variant = 'NaIon_COLD' if assembly_variant is None else assembly_variant
    _require(assembly_variant in ('NaIon_COLD', 'LTO_2S'), 'Unsupported boardview assembly variant: ' + str(assembly_variant))
    model_path = Path(model_path).resolve() if model_path is not None else None
    _require(model_path is None or model_path != cad_path, 'Boardview destination must differ from the assembly model')
    try:
        pcbnew = importlib.import_module('pcbnew')
    except ImportError:
        return _worker(pcb_path, cad_path, kicad_cli, assembly_variant=assembly_variant, model_path=model_path)
    source_hash = _digest(pcb_path)
    board = pcbnew.LoadBoard(str(pcb_path))
    _require(board.GetCopperLayerCount() == 2, 'Boardview validation currently supports two copper layers')
    footprints = list(board.GetFootprints())
    native = {f.GetReference(): f for f in footprints}
    _require(len(native) == len(footprints), 'Duplicate native component references')
    _require(all(ref and fp.GetValue().strip() for ref, fp in native.items()), 'Empty native reference/value')
    assembly = _assembly_metadata(native, assembly_variant, model_path)
    cli = str(Path(shutil.which(str(kicad_cli)) or kicad_cli).resolve())
    cad_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.boardview-', dir=cad_path.parent) as folder:
            temporary = Path(folder)
            raw = temporary / 'native.cad'
            command = [cli, 'pcb', 'export', 'gencad', '--unique-footprints', '-o', str(raw), pcb_path.name]
            proc = subprocess.run(command, cwd=pcb_path.parent, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=180)
            _require(proc.returncode == 0 and raw.is_file(), 'Native GenCAD export failed: ' + (proc.stderr or proc.stdout)[-4000:])
            repaired, corrections = _repair(raw.read_text('utf-8-sig'), native, pcbnew, assembly['component_device_text'])
            text = _normalize_units(repaired)
            counts = _validate(text, board, native, pcbnew, assembly['component_device_text'])
            _require(_digest(pcb_path) == source_hash, 'Native PCB changed during boardview export')
            _require(model_path is None or _digest(model_path) == assembly['model_sha256'], 'Assembly model changed during boardview export')
            ready = temporary / 'checked.cad'
            ready.write_text(text, 'utf-8', newline='\n')
            cad_hash = _digest(ready)
            report = {'status': 'PASS', 'format': 'GenCAD 1.4', 'units': 'THOU',
                      'pcb_sha256': source_hash, 'cad_sha256': cad_hash, 'native_export_sha256': _digest(raw),
                      'pcb_file': pcb_path.name, 'cad_file': cad_path.name,
                      'revision': board.GetTitleBlock().GetRevision(), 'kicad_version': pcbnew.Version(),
                      **corrections, **counts, **assembly, 'pcb_unchanged': True, 'model_unchanged': True,
                      'validation_scope': 'Native PCB/file comparison only; this build does not claim a GUI check.'}
            ready.replace(cad_path)
            return report
    finally:
        _require(_digest(pcb_path) == source_hash, 'Native PCB changed during boardview export')
        _require(model_path is None or _digest(model_path) == assembly['model_sha256'], 'Assembly model changed during boardview export')


if __name__ == '__main__':
    if len(sys.argv) not in (6, 7) or sys.argv[1] != '--worker':
        raise SystemExit('Use export_boardview(pcb_path, cad_path, kicad_cli) from the release tool.')
    try:
        options = json.loads(sys.argv[6]) if len(sys.argv) == 7 else {}
        result = export_boardview(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], **options)
        Path(sys.argv[5]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
