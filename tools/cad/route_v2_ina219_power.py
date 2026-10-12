"""Finish only new current-monitor and changed battery/interface branches."""
from pathlib import Path
import argparse, json, math, sys
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from complete_v2_routes import route, component_points, xy, vec
from patch_v2_ina219_power import ROOT,PROJECT,PCB,AUDIT,NEW,describe,sha
sys.path.insert(0,str(ROOT/'tools'))
from audit_v2_routing_engineering import TraceGraph,uid
HELD=[]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--route',action='store_true');args=ap.parse_args()
    b=k.LoadBoard(str(PCB));HELD.append(b);fps={f.GetReference():f for f in b.GetFootprints()}
    model=json.loads((PROJECT/'model.json').read_text(encoding='utf-8'));parts={p['ref']:p for p in model['parts']}
    def pad(r,p):return next(x for x in fps[r].Pads() if x.GetNumber()==str(p))
    nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
    log=[]
    def delete(t,why):log.append(dict(remove=describe(t),reason=why));b.Remove(t);HELD.append(t)
    if args.prepare:
        poses={'R73':(54,9.8,0),'C63':(60.4,8.0,0),'C64':(57.8,7.7,90)}
        for ref,(x,y,a) in poses.items():
            fps[ref].SetPosition(vec((x,y)));fps[ref].SetOrientationDegrees(a);parts[ref].update(x=x,y=y,rotation=a)
        # Native connectivity propagation may reassign a former ground stitch
        # sitting inside a new pad. Restore first, then remove only collisions.
        old=k.LoadBoard(str(AUDIT/'before_power.kicad_pcb'));HELD.append(old)
        original={uid(t):t.GetNetname() for t in old.GetTracks()}
        for t in list(b.GetTracks()):
            if original.get(uid(t))=='GND':
                t.SetNet(nets['GND'])
                collision=False
                if isinstance(t,k.PCB_VIA):
                    for ref in NEW:
                        for p in fps[ref].Pads():
                            if p.GetNetname()!='GND' and p.HitTest(t.GetPosition(),k.FromMM(.55)):collision=True
                # Remove obsolete explicit GND spokes of repurposed lands.
                if not isinstance(t,k.PCB_VIA):
                    for pin in (10,12):
                        p=pad('J101',pin)
                        if p.HitTest(t.GetStart(),k.FromMM(.25)) or p.HitTest(t.GetEnd(),k.FromMM(.25)):collision=True
                if collision:delete(t,'ground stitch/spoke conflicts with a newly assigned monitor or interface land')
        # Pin7 becomes a separate upper-supply return, not a fourth FILTER_OUT.
        p=pad('J101',7)
        for t in list(b.GetTracks()):
            if t.GetNetname()!='FILTER_OUT':continue
            if p.HitTest(t.GetStart(),k.FromMM(.65)) or p.HitTest(t.GetEnd(),k.FromMM(.65)):delete(t,'old FILTER_OUT branch at repurposed J101.7')
        # Prune only known raw/system split endpoints; preserve the complete
        # C53->TPS local bypass/input path, all charger feedback and hot loops.
        for t in list(b.GetTracks()):
            if uid(t) in {'4f36bd88-57e5-4291-bd38-f330c925e987','b875e0cd-e932-4e85-97d9-56d636054f75','5eeb2e38-822a-4c38-9f94-b7035e7da144','6653b44a-444b-47c5-a074-d1b06263293e','c998e180-ade1-4be1-a0fa-14542eaea26c'}:delete(t,'dangling end created by intentional raw/system partition')
        (PROJECT/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
        k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(PCB),b)
        (AUDIT/'prepare_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(prepared=True,removed=len(log),poses=poses)))
    if args.route:
        # Pad centres may be off the 0.1mm route grid; the route starts/ends
        # inside their copper lands, preserving strict octilinear segments.
        jobs=[
            ('BAT','R71',2,'J8',1,.8),
            ('BAT','R71',2,'J12',1,.8),
            ('BAT','TP1',1,'R71',2,.25),
            ('BAT','R15',1,'R71',2,.25),
            ('BAT_SYS','R71',1,'C53',1,.8),
            ('FILTER_OUT','L4',2,'J101',5,.8),
            ('INA_VIN_P','R72',2,'U12',8,.25),
            ('INA_VIN_M','R73',2,'U12',7,.25),
            ('INA_VIN_P','C64',1,'U12',8,.25),
            ('INA_VIN_M','C64',2,'U12',7,.25),
            ('SYS_3V3','C63',1,'U12',5,.3),
            ('SYS_3V3','J101',7,'C63',1,.3),
            ('SDA','J101',10,'U12',3,.25),
            ('SCL','J101',12,'U12',4,.25),
        ]
        for name,ra,pa,rb,pb,w in jobs:
            a,z=pad(ra,pa),pad(rb,pb);b.BuildConnectivity();g=TraceGraph(b)
            if g.path((ra,str(pa)),(rb,str(pb)),0)['found_without_zones']:continue
            sl=tuple(i for i,l in enumerate((k.F_Cu,k.B_Cu)) if a.IsOnLayer(l));el=tuple(i for i,l in enumerate((k.F_Cu,k.B_Cu)) if z.IsOnLayer(l))
            row=route(b,name,xy(a.GetPosition()),xy(z.GetPosition()),w,sl,el,source_points=component_points(b,a),target_points=component_points(b,z));row.update(start_pad=[ra,pa],end_pad=[rb,pb]);log.append(row)
            k.SaveBoard(str(PCB),b)
        # Separate Kelvin launches connect at the inner shunt land edge;
        # main current lands are treated as obstacles except the source pad.
        for net,ref,pin,target in [('BAT_SYS','R71',1,'R72'),('BAT','R71',2,'R73')]:
            a,z=pad(ref,pin),pad(target,1);b.BuildConnectivity()
            if TraceGraph(b).path((ref,str(pin)),(target,'1'),0)['found_without_zones']:continue
            changed=[]
            for t in b.GetTracks():
                if t.GetNetname()==net:changed.append(t);t.SetNet(nets['GND'])
            for f in b.GetFootprints():
                for p in f.Pads():
                    if p.GetNetname()==net and uid(p) not in (uid(a),uid(z)):changed.append(p);p.SetNet(nets['GND'])
            try:
                inner=xy(a.GetPosition());inner=(inner[0],inner[1]+(-.7 if pin==1 else .7))
                row=route(b,net,inner,xy(z.GetPosition()),.25,starts=(1,),ends=(1,))
                row.update(kind='separate_Kelvin_pickup',source_pad=[ref,pin],target_pad=[target,1]);log.append(row)
            finally:
                for t in changed:t.SetNet(nets[net])
            k.SaveBoard(str(PCB),b)
        k.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity();k.SaveBoard(str(PCB),b)
        (AUDIT/'route_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(routed=len(log),sha256=sha(PCB))))
if __name__=='__main__':main()
