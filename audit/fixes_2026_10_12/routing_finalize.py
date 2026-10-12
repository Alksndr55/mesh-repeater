from pathlib import Path
import sys,json,subprocess,math,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless()
import routing_router as r
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
b=k.LoadBoard(str(OUT/'routing_candidate12.kicad_pcb'));held=[];removed=[];added=[]
def uid(t):return str(t.m_Uuid.AsString())
# Remove three one-ended remnants without pins, and two dead return-via islands.
prune={'5dce3d9c-f5ee-4020-8f0b-7aab90f25eaf','e3c0f42a-0555-4296-9da4-aab66232cb27','111c4c71-7df7-494b-9e6d-c451242c1c05','a765aa46-732a-4a5d-b10d-736e8b4d5487','c8cfbe6c-fa26-466d-a963-1563162fadf6','612908dd-7103-4035-8646-f0cc295c4673'}
# Added GND router path made for a scratch default settings board is unnecessary;
# retain later direct ground stitching only, remove newly added GND copper paths.
candidate11=k.LoadBoard(str(OUT/'routing_candidate11.kicad_pcb'));ground_original={uid(t) for t in candidate11.GetTracks() if t.GetNetname()=='GND'}
for t in list(b.GetTracks()):
 if uid(t) in prune or t.GetNetname()=='GND' and uid(t) not in ground_original:
  removed.append({'uuid':uid(t),'net':t.GetNetname(),'at':r.xy(t.GetStart()),'end':r.xy(t.GetEnd())});b.Remove(t);held.append(t)
z=k.ZONE(b);z.SetIsRuleArea(True);z.SetZoneName('RF_GROUND_GUARD');z.SetLayer(k.B_Cu)
for meth in ['SetDoNotAllowTracks','SetDoNotAllowVias','SetDoNotAllowPads','SetDoNotAllowZoneFills','SetDoNotAllowFootprints']:getattr(z,meth)(False)
poly=z.Outline();poly.NewOutline()
for p in [[30.7,.4],[44.9,.4],[44.9,12],[30.7,12]]:v=r.vec(p);poly.Append(v.x,v.y)
b.Add(z)
P.with_suffix('.kicad_dru').write_text('''(version 1)
(rule "RF GND gap 0.25 mm"
 (layer F.Cu)
 (condition "((A.NetName == '/ANT_RF' || A.NetName == '/ANT_SMA') && B.NetName == 'GND') || ((B.NetName == '/ANT_RF' || B.NetName == '/ANT_SMA') && A.NetName == 'GND')")
 (constraint clearance (min 0.25mm)))
(rule "RF opposite layer permits GND and RF only"
 (layer B.Cu)
 (condition "A.intersectsArea('RF_GROUND_GUARD') && A.NetName != 'GND' && A.NetName != '/ANT_RF' && A.NetName != '/ANT_SMA'")
 (constraint disallow track via))
''',encoding='utf8')
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(P),b)
(OUT/'routing_final_cleanup.json').write_text(json.dumps({'removed':removed,'RF_rule_area':[30.7,.4,44.9,12],'rule_reference':'https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html#custom_design_rules'},indent=2),encoding='utf8')
print('Saved provisional native for full project DRC',flush=True)

