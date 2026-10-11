"""Prove preserved endpoint graph after joining the two cable connectors.

Names of automatic KiCad nets and sheet paths can change. Pin identity and
functional connected-component membership may not. This check compares the
exported native KiCad netlists rather than the schematic generator's manifest.
"""
from pathlib import Path
import argparse, hashlib, json, xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]

def load_netlist(path,board):
    xml=ET.parse(path).getroot();net_by_pin={};groups={}
    for net in xml.findall('.//nets/net'):
        key=(board,net.get('name'))
        nodes={(n.get('ref'),n.get('pin')) for n in net.findall('node') if not n.get('ref','').startswith('#')}
        groups[key]=nodes
        for node in nodes:
            assert (board,*node) not in net_by_pin,('Duplicate native pin',board,node)
            net_by_pin[(board,*node)]=key
    components={n.get('ref'):n for n in xml.findall('.//components/comp')}
    return net_by_pin,groups,components

class Union:
    def __init__(self):self.parents={}
    def root(self,n):
        self.parents.setdefault(n,n)
        while self.parents[n]!=n:
            self.parents[n]=self.parents[self.parents[n]];n=self.parents[n]
        return n
    def join(self,a,b):self.parents[self.root(a)]=self.root(b)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--contract',type=Path,required=True)
    p.add_argument('--power-netlist',type=Path,required=True)
    p.add_argument('--logic-netlist',type=Path,required=True)
    p.add_argument('--power-model',type=Path,required=True)
    p.add_argument('--logic-model',type=Path,required=True)
    p.add_argument('--cable',type=Path,required=True,help='JSON: connections with power.ref/pin, logic.ref/pin, and net')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    for name,path in vars(a).items():
        if isinstance(path,Path):
            if not path.resolve().is_relative_to(ROOT):raise ValueError('All v2 proof paths must stay inside v2')
            setattr(a,name,path.resolve())
    contract=json.loads(a.contract.read_text(encoding='utf-8'))
    cable=json.loads(a.cable.read_text(encoding='utf-8'))
    models={n:json.loads(path.read_text(encoding='utf-8')) for n,path in [('POWER',a.power_model),('LOGIC',a.logic_model)]}
    natives={n:load_netlist(path,n) for n,path in [('POWER',a.power_netlist),('LOGIC',a.logic_netlist)]}
    checks=[]
    def check(name,passed,detail=None):checks.append({'name':name,'pass':bool(passed),'detail':detail})
    union=Union()
    for board,model in models.items():
        expected_local={};pin_missing=[];native_local={}
        for part in model['parts']:
            for pin,logical in part['nets'].items():
                endpoint=(part['ref'],str(pin))
                key=natives[board][0].get((board,*endpoint))
                if key is None:pin_missing.append(endpoint);continue
                # Each declared NC is an isolated one-pin native component.
                declared=('NC',*endpoint) if logical is None else ('NET',logical)
                expected_local.setdefault(declared,set()).add(endpoint)
                native_local.setdefault(key,set()).add(endpoint)
        eg={frozenset(nodes) for nodes in expected_local.values()};ng={frozenset(nodes) for nodes in native_local.values()}
        check(board+' native graph equals saved model',not pin_missing and eg==ng,{'missing_pins':pin_missing,'missing_groups':[sorted(v) for v in eg-ng],'extra_groups':[sorted(v) for v in ng-eg]})
    for native in natives.values():
        for group in native[1]:union.root(group)
    contacts=[];cable_nets=set()
    for link in cable['connections']:
        ends=[]
        for board,key in [('POWER','power'),('LOGIC','logic')]:
            endpoint=(board,link[key]['ref'],str(link[key]['pin']))
            ends.append(natives[board][0].get(endpoint))
        check('cable contacts exist: '+str(link),all(ends))
        if all(ends):
            declared=[]
            for board,key in [('POWER','power'),('LOGIC','logic')]:
                cp=next(z for z in models[board]['parts'] if z['ref']==link[key]['ref'])
                declared.append(cp['nets'][str(link[key]['pin'])])
            check('cable same electrical net: '+str(link),declared==[link['net'],link['net']],declared)
            union.join(*ends);cable_nets.add(link['net']);contacts.append((ends,link['net']))
    check('exact four interboard nets',cable_nets=={'FILTER_OUT','BAT','MODE','GND'},sorted(cable_nets))
    source_parts={p['reference']:p for p in contract['parts']}
    # A documented removed SH1 is mechanical. It never removes a functional
    # signal endpoint. Grounded bolt pads are new mechanical GND endpoints.
    actual_parts={board:{p['ref']:p for p in m['parts']} for board,m in models.items()}
    removed=[r for r in source_parts if r not in actual_parts[source_parts[r]['board']]]
    mechanical_refs={r for r,part in source_parts.items() if part['original_model_part']['kind']=='MountingHole'}|{'SH1'}
    check('all original functional references retained',set(removed).issubset(mechanical_refs),removed)
    expected_groups={};actual_groups={};nc_fail=[];value_fail=[];variant_fail=[];pin_fail=[]
    for logical in contract['nets']:
        nodes=[]
        for n in logical['nodes']:
            if n['reference'] in removed or source_parts[n['reference']]['original_model_part']['kind']=='MountingHole':continue
            endpoint=(n['board'],n['reference'],str(n['pin']))
            native=natives[n['board']][0].get(endpoint)
            if native is None:pin_fail.append(endpoint);continue
            nodes.append((n['reference'],str(n['pin'])))
            actual_groups.setdefault(union.root(native),set()).add((n['reference'],str(n['pin'])))
        if nodes:expected_groups[logical['logical_net']]=set(nodes)
    expected={frozenset(nodes) for nodes in expected_groups.values()}
    actual={frozenset(nodes) for nodes in actual_groups.values()}
    check('all connected functional pins exist',not pin_fail,pin_fail)
    check('functional pin graph equals S4.16 across cable',expected==actual,{'expected_groups':len(expected),'actual_groups':len(actual),'missing_groups':[sorted(v) for v in expected-actual],'extra_groups':[sorted(v) for v in actual-expected]})
    for ref,source in source_parts.items():
        if ref in removed:continue
        board=source['board'];original=source['original_model_part'];part=actual_parts[board].get(ref)
        if part is None:continue
        if original['kind']=='MountingHole':continue
        for pin,info in source['exact_netpins'].items():
            if not info['no_connect']:continue
            node=(board,ref,pin);net=natives[board][0].get(node)
            if net is None or natives[board][1].get(net,set())!={(ref,pin)}:nc_fail.append(node)
        # Value, fit policy and variant values are preserved even when the
        # connector's MPN/footprint must change to obtain side access.
        expected_value=source['assembly_variant_row']['Value_NaIon']
        component=natives[board][2].get(ref)
        mechanical=original['kind'].startswith('Connector') or original['kind']=='Switch'
        if component is None or (not mechanical and component.findtext('value')!=expected_value):value_fail.append((board,ref,expected_value,None if component is None else component.findtext('value')))
        if component is not None:
            props={v.get('name'):v.get('value') for v in component.findall('property')}
            fields=['Fit_NaIon','Fit_LTO_2S','Fit_NaIon_NoCold']+([] if mechanical else ['Value_NaIon','Value_LTO_2S','Value_NaIon_NoCold'])
            for field in fields:
                if props.get(field)!=source['assembly_variant_row'][field]:variant_fail.append((board,ref,field,source['assembly_variant_row'][field],props.get(field)))
    check('original NC pins remain isolated',not nc_fail,nc_fail)
    check('default component values unchanged',not value_fail,value_fail)
    check('all three assembly fit/value variants unchanged',not variant_fail,variant_fail)
    projected={name:nodes for name,nodes in expected_groups.items()}
    filter_group=next((group for group,nodes in actual_groups.items() if ('J11','1') in nodes),None)
    sys_group=next((group for group,nodes in actual_groups.items() if ('J11','2') in nodes),None)
    check('J11 removed keeps LC OUT separate from SYS_3V3',filter_group is not None and sys_group is not None and filter_group!=sys_group)
    check('D3/D4 remain local to POWER',all(ref in actual_parts['POWER'] and ref not in actual_parts['LOGIC'] for ref in ['D3','D4','R10','R11']))
    input_paths=[a.contract,a.power_netlist,a.logic_netlist,a.power_model,a.logic_model,a.cable]
    for model_path in [a.power_model,a.logic_model]:
        for pattern in ['*.kicad_sch','*.kicad_sym','*.kicad_pro']:
            input_paths.extend(sorted(model_path.parent.glob(pattern)))
    report={'scope':'Native schematic graph after cable connection; no board/bench/mechanical claim','baseline_pcb_sha256':contract['source_inputs']['pcb']['sha256'],'ok':all(c['pass'] for c in checks),'checks':checks,'inputs':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in input_paths}}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ok':report['ok'],'checks':len(checks),'failed':[c for c in checks if not c['pass']],'report':str(a.out.relative_to(ROOT))},ensure_ascii=True))
    if not report['ok']:raise SystemExit(1)
if __name__=='__main__':main()
