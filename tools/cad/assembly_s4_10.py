"""Assembly instructions without native DNP strikeouts, requested in S4.10."""
from pathlib import Path
import json

def apply(model):
    model['parts']=[p for p in model['parts'] if p['ref'] not in ('R18','TP5')]
    next(p for p in model['parts'] if p['ref']=='U2')['nets']['5']=None
    snapshot=Path(__file__).with_name('reports')/'s4_10_placements.json'
    placement=json.loads(snapshot.read_text(encoding='utf8'))['placement'] if snapshot.exists() else {}
    for p in model['parts']:
        fit_na=p.get('fit_naion',not p.get('dnp',False))
        fit_lto=p.get('fit_lto2s',p.get('group')=='lto_balancer' or fit_na)
        p.update(fit_naion=fit_na,fit_lto2s=fit_lto,assembly_default_dnp=not fit_na,dnp=False)
        p['assembly']='Na-ion: '+('FIT' if fit_na else 'DNP')+'; LTO 2S: '+('FIT' if fit_lto else 'DNP')
        if p['ref'] in placement:p.update(placement[p['ref']])
    model.update(revision='S4_10_BALANCER_SHIELD',schematic_revision='S4.10',schematic_date='2026-10-10')
    model['assembly_policy']={
        'native_dnp':False,
        'reason':'User requested schematic without DNP strikeouts; assembly is specified by labels and explicit Fit_NaIon / Fit_LTO_2S fields.',
        'default':'Na-ion',
        'bom_rule':'Use variant fit fields; native DNP no longer filters optional positions.',
    }
    model['balancer_layout']={'location':'inside common SH1 cover with CN3722 and TPS63802',
                             'input_connector':'J12',
                             'branches':{'1':'BAT to R47.1','2':'LTO_MID to upper return and R51.1','3':'GND to lower return'},
                             'series_resistors_ohm':2}
    model['removed_s4_10']={'references':['R18','TP5'],'net':'PG_SYS','unused_pin':'U2.5 PG marked NC'}

def fields(part):
    """Explicit machine-readable fields for BOM and PCB/SCH parity."""
    value=part['value']
    lto=part.get('value_lto2s',{'R3':'13k 0.1% <=25ppm/C','R4':'10.5k 0.1% <=25ppm/C','C30':'6.8pF 50V C0G'}.get(part['ref'],value))
    from component_nominal import nominal
    lto_mpn=part.get('mpn_lto2s','MPN not selected' if part['ref'] in ('R3','R4','C30') else part.get('mpn',''))
    return {'Fit_NaIon':'yes' if part['fit_naion'] else 'no',
            'Fit_LTO_2S':'yes' if part['fit_lto2s'] else 'no',
            'Value_NaIon':value,'Value_LTO_2S':lto,'Assembly':part['assembly'],
            'Nominal':nominal(part),'MPN_NaIon':part.get('mpn',''),'MPN_LTO_2S':lto_mpn,
            'Fit_NaIon_NoCold':'yes' if part.get('fit_naion_no_cold',part['fit_naion']) else 'no',
            'Value_NaIon_NoCold':part.get('value_naion_no_cold',value),
            'MPN_NaIon_NoCold':part.get('mpn_naion_no_cold',part.get('mpn',''))}
