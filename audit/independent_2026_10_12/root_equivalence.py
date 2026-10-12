"""Second implementation: compare freshly exported native source and V2 graphs."""
from pathlib import Path
import csv, hashlib, json, subprocess, xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
source = ROOT / 'baseline/S4_16/Meshcore_NaIon.kicad_sch'
command = [r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe', 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', str(OUT/'root_source.xml'), str(source)]
p = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
if p.returncode:
    raise RuntimeError(p.stdout + p.stderr)

def load(path, board):
    xml = ET.parse(path).getroot()
    components = {c.get('ref'): c for c in xml.findall('./components/comp')}
    groups, bypin = {}, {}
    for i, net in enumerate(xml.findall('./nets/net')):
        ident = (board, i)
        nodes = {(n.get('ref'), n.get('pin')) for n in net.findall('node') if not n.get('ref', '').startswith('#')}
        groups[ident] = nodes
        for node in nodes:
            if node in bypin:
                raise ValueError(('duplicate endpoint', board, node))
            bypin[node] = ident
    return components, groups, bypin

source_c, source_g, source_p = load(OUT/'root_source.xml', 'SOURCE')
v2 = {b:load(OUT/('electrical.' + b.lower() + '.xml'), b) for b in ('POWER', 'LOGIC')}
allowed = set(source_p) - {p for p in source_p if p[0] == 'SH1'}
parents = {}
def root(x):
    parents.setdefault(x, x)
    if parents[x] != x:
        parents[x] = root(parents[x])
    return parents[x]
def union(x,y):
    parents[root(x)] = root(y)
for _, groups, _ in v2.values():
    for g in groups:
        root(g)
cable_checks = []
for pin in range(1,13):
    a = v2['POWER'][2][('J101',str(pin))]
    b = v2['LOGIC'][2][('J201',str(pin))]
    union(a,b)
    cable_checks.append({'power_pin':pin, 'logic_pin':pin})
expected = {frozenset(nodes & allowed) for nodes in source_g.values() if nodes & allowed}
merged = {}
seen = set()
for board, (_, groups, bypin) in v2.items():
    for g, nodes in groups.items():
        original_nodes = nodes & allowed
        seen.update(original_nodes)
        if original_nodes:
            merged.setdefault(root(g),set()).update(original_nodes)
actual = {frozenset(nodes) for nodes in merged.values()}
missing_pins = sorted(allowed - seen)
missing_groups = [sorted(g) for g in expected-actual]
extra_groups = [sorted(g) for g in actual-expected]

variants = list(csv.DictReader((ROOT/'baseline/S4_16/assembly_variants_S4_16.csv').open(encoding='utf-8-sig',newline='')))
bom = {r['Reference']:r for r in csv.DictReader((ROOT/'bom/V2_COMPONENT_BOM.csv').open(encoding='utf-8-sig',newline=''))}
mechanical = {'J3','J5','J7','J8','J11','J12','SW1','SW2','H1','H2','H3','H4'}
fieldmap = [('Value_NaIon','Value_NaIon_COLD'), ('Fit_NaIon','Fit_NaIon_COLD'), ('MPN_NaIon','MPN_NaIon_COLD'), ('Value_NaIon_NoCold','Value_NaIon_NoCOLD'), ('Fit_NaIon_NoCold','Fit_NaIon_NoCOLD'), ('MPN_NaIon_NoCold','MPN_NaIon_NoCOLD'), ('Value_LTO_2S','Value_LTO_2S'), ('Fit_LTO_2S','Fit_LTO_2S'), ('MPN_LTO_2S','MPN_LTO_2S')]
variant_differences = []
native_differences = []
allowed_mechanical_differences = []
for row in variants:
    ref = row['Reference']
    if ref == 'SH1':
        continue
    parts = [(b,c[ref]) for b,(c,_,_) in v2.items() if ref in c]
    if len(parts) != 1:
        native_differences.append({'ref':ref,'copies':len(parts)})
        continue
    component = parts[0][1]
    props = {x.get('name'):x.get('value') for x in component.findall('property')}
    for src, dst in fieldmap:
        if ref in mechanical and src.startswith(('Value_','MPN_')):
            if bom[ref][dst] != row[src] or props.get(src) != row[src]:
                allowed_mechanical_differences.append({'ref':ref,'field':src,'source':row[src],'bom':bom[ref][dst],'native':props.get(src),'reason':'Side-access component selection or grounded M3 clamp land required by V2 task'})
            continue
        if bom[ref][dst] != row[src]:
            variant_differences.append({'ref':ref,'field':dst,'source':row[src],'v2':bom[ref][dst]})
        if props.get(src) != row[src]:
            native_differences.append({'ref':ref,'field':src,'source':row[src],'v2':props.get(src)})
allparts = {ref:(b,comp) for b,(comps,_,_) in v2.items() for ref,comp in comps.items()}
removed_refs = sorted(set(source_c)-set(allparts))
filter_g = root(v2['LOGIC'][2][('J11','1')])
sys_g = root(v2['LOGIC'][2][('J11','2')])
data = {'method':'Fresh SOURCE native XML; merged POWER/LOGIC net components through twelve physical 1:1 cable contacts. No generator contract used.', 'source_pins_retained':len(allowed),'source_groups':len(expected),'v2_groups':len(actual),'missing_pins':missing_pins,'missing_groups':missing_groups,'extra_groups':extra_groups,'removed_refs':removed_refs,'bom_variant_differences':variant_differences,'native_variant_differences':native_differences,'J11_removed_FILTER_SYS_separate':filter_g != sys_g,'source_export':{'command':command,'stdout':p.stdout,'stderr':p.stderr},'inputs':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [source,OUT/'root_source.xml',OUT/'electrical.power.xml',OUT/'electrical.logic.xml',ROOT/'bom/V2_COMPONENT_BOM.csv',ROOT/'baseline/S4_16/assembly_variants_S4_16.csv']}}
data['pass'] = not any([missing_pins,missing_groups,extra_groups,variant_differences,native_differences]) and removed_refs == ['SH1'] and filter_g != sys_g
data['documented_mechanical_exceptions'] = allowed_mechanical_differences
(OUT/'root_equivalence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k not in ('inputs','source_export')},ensure_ascii=False))
