"""Fresh read-only final independent PCB geometry plus electrical review.

Run only after both board owners hand off BOARD_FINAL_READY. Does not refill,
SaveBoard, edit CAD or alter earlier A2 reports. CLI DRC is read-only.
"""
from pathlib import Path
import sys,json,hashlib,math,re,collections
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.stdout.reconfigure(encoding='utf-8')
sys.path[:0]=[str(OUT),str(ROOT/'tools'),str(ROOT/'tools/cad')]
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
import independent_electrical_native as electrical
from sync_v2_native_metadata import parse
HELD=[];TOKENS={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(p):return (round(k.ToMM(p.x),6),round(k.ToMM(p.y),6))
def uid(p):return p.m_Uuid.AsString()
def vec(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
def pointseg(p,a,b):
 dx=b[0]-a[0];dy=b[1]-a[1];ll=dx*dx+dy*dy
 q=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/ll)) if ll else 0
 return math.dist(p,(a[0]+q*dx,a[1]+q*dy))
def grid3(p):return all(abs((v-1.5)/3-round((v-1.5)/3))<1e-6 for v in p)
def normalize_node(node):
 if isinstance(node,str):return node
 if node and node[0] in ('filled_polygon','fill_segments'):return None
 return [n for child in node if (n:=normalize_node(child)) is not None]
def class_tokens(path,name):
 if path not in TOKENS:TOKENS[path]=parse(path.read_text(encoding='utf8'))
 return sorted([normalize_node(n) for n in TOKENS[path][1:] if isinstance(n,list) and n and n[0]==name],key=lambda n:json.dumps(n,separators=(',',':')))
def metrics(board):
 tracks=[t for t in board.GetTracks() if not isinstance(t,k.PCB_VIA)]
 vias=[t for t in board.GetTracks() if isinstance(t,k.PCB_VIA)]
 graph=collections.defaultdict(list);bad=[]
 for t in tracks:
  a,z=xy(t.GetStart()),xy(t.GetEnd());dx,dy=abs(a[0]-z[0]),abs(a[1]-z[1])
  if min(dx,dy)>2e-6 and abs(dx-dy)>2e-6:bad.append({'uuid':uid(t),'net':t.GetNetname(),'a':a,'z':z})
  key=(t.GetNetCode(),t.GetLayer(),t.GetWidth())
  graph[key,a].append((z,uid(t)));graph[key,z].append((a,uid(t)))
 turns=0;non45_90=[]
 for (key,at),edges in graph.items():
  if len(edges)!=2:continue
  a,z=edges[0][0],edges[1][0]
  incoming=(at[0]-a[0],at[1]-a[1]);outgoing=(z[0]-at[0],z[1]-at[1])
  if math.hypot(*incoming)<1e-8 or math.hypot(*outgoing)<1e-8:continue
  cosine=max(-1,min(1,(incoming[0]*outgoing[0]+incoming[1]*outgoing[1])/(math.hypot(*incoming)*math.hypot(*outgoing))))
  angle=math.degrees(math.acos(cosine))
  if angle>.01:
   turns+=1
   if min(abs(angle-v) for v in (45,90))>.01:
    participating={e[1] for e in edges};net,layer,width=key
    pad_contacts=[f.GetReference()+'.'+p.GetNumber() for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode()==net and p.IsOnLayer(layer) and p.GetEffectiveShape(layer).Collide(vec(at),0)]
    via_contacts=[uid(v) for v in vias if v.GetNetCode()==net and v.IsOnLayer(layer) and v.GetEffectiveShape(layer).Collide(vec(at),0)]
    branches=[uid(t) for t in tracks if uid(t) not in participating and t.GetNetCode()==net and t.GetLayer()==layer and pointseg(at,xy(t.GetStart()),xy(t.GetEnd()))<1e-6]
    non45_90.append({'at':at,'angle':angle,'track_UUIDs':[e[1] for e in edges],'pad_contacts':pad_contacts,'via_contacts':via_contacts,'actual_other_centreline_branches':branches,'bare_copper_degree2_reversal':not (pad_contacts or via_contacts or branches)})
 lengths=[math.dist(xy(t.GetStart()),xy(t.GetEnd())) for t in tracks]
 grounds={uid(v):{'at':xy(v.GetPosition()),'diameter':k.ToMM(v.GetWidth(k.F_Cu)),'drill':k.ToMM(v.GetDrill()),'layers':v.GetLayerSet().FmtHex(),'net':v.GetNetname()} for v in vias if v.GetNetname()=='GND'}
 return {'segments':len(tracks),'turns':turns,'length_mm':sum(lengths),'micro_segments_under_0_25_mm':sum(l<.25-1e-8 for l in lengths),'micro_segments_under_0_5_mm':sum(l<.5-1e-8 for l in lengths),'gnd_vias':len(grounds),'gnd_vias_on_3mm_grid':sum(grid3(v['at']) for v in grounds.values()),'all_vias':len(vias),'segments_outside_0_45_90':bad,'turns_outside_45_90':non45_90},grounds
def authorized_digital_reroute_check():
 """Old exact geometry clause is superseded by this task's route cleanup.

 Keep immutable RF; independently prove same digital pad memberships,
 anchored plated barrels, width/layer sets, complete actual copper paths and
 no length increase for each formerly repaired net. No authoring model input.
 """
 prior_path=ROOT/'audit/ina219_and_vertical_2026_10_12/before/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
 if not prior_path.exists():prior_path=ROOT/'audit/ina219_vertical_interconnect_2026_10_12/MeshRepeater2_Logic_before.kicad_pcb'
 current_path=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
 old=k.LoadBoard(str(prior_path));new=k.LoadBoard(str(current_path));HELD.extend((old,new))
 contract=json.loads((ROOT/'design/v2_electrical_contract.json').read_text(encoding='utf8'))
 aliases={pin['native_net']:pin['logical_net'] for part in contract['parts'] for pin in part['exact_netpins'].values()}
 logical=lambda net:aliases.get(net,net.split('/')[-1])
 def rows(b,nets):
  out=[]
  for t in b.GetTracks():
   net=logical(t.GetNetname())
   if net not in nets:continue
   if isinstance(t,k.PCB_VIA):r=('via',net,xy(t.GetPosition()),t.GetDrill(),t.GetWidth(k.F_Cu),t.GetLayerSet().FmtHex())
   else:r=('track',net,tuple(sorted((xy(t.GetStart()),xy(t.GetEnd())))),t.GetWidth(),int(t.GetLayer()))
   out.append(r)
  return sorted(out)
 RF={'ANT_RF','ANT_SMA'};rf_pass=rows(old,RF)==rows(new,RF)
 G=electrical.TraceGraph(new);details={};all_pass=rf_pass
 for net in ('MOSI_RF','MISO_MCU','RADIO_RST','RADIO_RXEN'):
  def memberships(b):return sorted({(f.GetReference(),p.GetNumber()) for f in b.GetFootprints() for p in f.Pads() if p.GetNumber() and logical(p.GetNetname())==net})
  op,np=memberships(old),memberships(new)
  def copper(b):return [t for t in b.GetTracks() if not isinstance(t,k.PCB_VIA) and logical(t.GetNetname())==net]
  ot,nt=copper(old),copper(new)
  old_widths=sorted({(t.GetWidth(),int(t.GetLayer())) for t in ot});new_widths=sorted({(t.GetWidth(),int(t.GetLayer())) for t in nt})
  old_length=sum(math.dist(xy(t.GetStart()),xy(t.GetEnd())) for t in ot);new_length=sum(math.dist(xy(t.GetStart()),xy(t.GetEnd())) for t in nt)
  old_vias=[r for r in rows(old,{net}) if r[0]=='via'];new_vias=[r for r in rows(new,{net}) if r[0]=='via']
  paths=[G.path(np[0],end,0) for end in np[1:]] if np else []
  passed=op==np and bool(np) and old_widths==new_widths and old_vias==new_vias and new_length<=old_length+1e-6 and all(p['found_without_zones'] for p in paths)
  details[net]={'pass':passed,'old_pad_endpoints':op,'new_pad_endpoints':np,'old_width_layers':old_widths,'new_width_layers':new_widths,'barrels_exact':old_vias==new_vias,'old_length_mm':old_length,'new_length_mm':new_length,'actual_current_routes':paths}
  all_pass &= passed
 return bool(all_pass),{'RF_exact_saved_geometry':rf_pass,'digital_nets':details,'authorization_scope':'Current user requests fewer turns and straight tracks on both boards. Original RF and repaired logical endpoints are retained; previous exact-segment geometry clause would require restoring the microstairs being removed.'}
def main():
 inputs={};checks=[];boards={}
 def bind(p):inputs[p.relative_to(ROOT).as_posix()]=sha(p)
 def check(n,p,d=None):checks.append({'name':n,'pass':bool(p),'detail':d})
 # Same source code/method as former 84-check review, now own outputs/inputs.
 original=ROOT/'audit/ina219_and_vertical_2026_10_12/independent_review_native.py'
 copied=OUT/'independent_electrical_native.py'
 bind(original);bind(copied);bind(Path(__file__))
 check('Independent electrical method exact copy of previous reviewer',sha(original)==sha(copied))
 sys.argv=[str(copied),'--scope','final']
 try:electrical.main()
 except SystemExit as exc:
  if exc.code not in (0,1):raise
 electrical_path=OUT/'independent_final_native_measurements.json';bind(electrical_path)
 E=json.loads(electrical_path.read_text(encoding='utf8'))
 historical_clause='Prior short SPI/RESET and repaired RXEN/RF geometry retained'
 failed_electrical=[c for c in E['checks'] if not c['pass']]
 if any(c['name']!=historical_clause for c in failed_electrical):
  raise RuntimeError('Fresh electrical failure beyond the authorized reroute clause: '+json.dumps(failed_electrical,ensure_ascii=True))
 revised_check,revised_detail=authorized_digital_reroute_check()
 for c in E['checks']:
  if c['name']==historical_clause:
   c={'name':'Prior repaired SPI/RESET/RXEN functions retained under authorized straightening; RF geometry exact','pass':revised_check,'detail':{'superseded_historical_exact_geometry_clause':c,'current_native_proof':revised_detail}}
  checks.append(c)
 inputs.update(E['inputs'])
 inventory=OUT/'GND_before_analysis.json';proposals=OUT/'GND_before_candidates.json'
 bind(inventory);bind(proposals)
 P=json.loads(proposals.read_text(encoding='utf8'))
 for name in ('POWER','LOGIC'):
  title=name.title();relative=Path(f'design/MeshRepeater2_{title}/MeshRepeater2_{title}.kicad_pcb')
  before=OUT/'before'/relative;after=ROOT/relative
  bind(before);bind(after)
  old=k.LoadBoard(str(before));new=k.LoadBoard(str(after));HELD.extend((old,new))
  bm,bvias=metrics(old);am,avias=metrics(new)
  moved=[{'uuid':u,'from':v['at'],'to':avias[u]['at']} for u,v in bvias.items() if u in avias and v['at']!=avias[u]['at']]
  boards[name]={'before':bm,'after':am,'gnd_vias_moved':len(moved),'moves':moved}
  check(name+' footprints and every component field/pad/pose unchanged',class_tokens(before,'footprint')==class_tokens(after,'footprint'))
  for typ in ('net','setup','layers','general','gr_line','gr_arc','gr_rect','gr_poly','gr_text','dimension','group','target','zone'):
   check(name+' native '+typ+' settings/geometry unchanged except filled polygons',class_tokens(before,typ)==class_tokens(after,typ))
  check(name+' no GND stitch added or deleted; barrel dimensions preserved',set(bvias)==set(avias) and all({k:v[k] for k in ('diameter','drill','layers','net')}=={k:avias[u][k] for k in ('diameter','drill','layers','net')} for u,v in bvias.items()),{'before':len(bvias),'after':len(avias),'moved':moved})
  protected=next(b['protected'] for b in P['boards'] if b['board'].upper()==name)
  bad=[r for r in protected if r.get('electrical_protected') and (r['uuid'] not in avias or avias[r['uuid']]['at']!=tuple(r['at_mm']))]
  check(name+' RF/local-island/track/pad-return protected vias stay exact',not bad,bad)
  check(name+' all saved segments use straight 0/45/90 geometry',not am['segments_outside_0_45_90'],am['segments_outside_0_45_90'])
  bare=[t for t in am['turns_outside_45_90'] if t['bare_copper_degree2_reversal']]
  check(name+' no bare trace degree2 corners reverse by135/180degrees',not bare,bare)
  check(name+' degree2 same-net/layer/width bends strictly reduced',am['turns']<bm['turns'],{'before':bm['turns'],'after':am['turns']})
  check(name+' unnecessary microsegments and segment count reduced',am['segments']<bm['segments'] and am['micro_segments_under_0_25_mm']<bm['micro_segments_under_0_25_mm'],{'before_segments':bm['segments'],'after_segments':am['segments'],'before_micro':bm['micro_segments_under_0_25_mm'],'after_micro':am['micro_segments_under_0_25_mm']})
  check(name+' copper centreline length not increased',am['length_mm']<=bm['length_mm']+1e-5,{'before':bm['length_mm'],'after':am['length_mm']})
  # Recheck actual combined filled zones/tracks/pads and plated-barrel graph.
  _,components=electrical.physical_ground(new)
  check(name+' all saved GND copper physically one component',len(components)==1,components)
  # Non-GND vias are connection anchors and must be left unchanged.
  def via_map(b):return {uid(v):(xy(v.GetPosition()),v.GetNetname(),v.GetDrill(),v.GetWidth(k.F_Cu),v.GetLayerSet().FmtHex()) for v in b.GetTracks() if isinstance(v,k.PCB_VIA) and v.GetNetname()!='GND'}
  check(name+' all non-GND vias unchanged',via_map(old)==via_map(new))
 changed=[p for p,h in inputs.items() if sha(ROOT/p)!=h]
 check('All independently reviewed inputs stayed unchanged',not changed,changed)
 raw_review={'path':electrical_path.relative_to(ROOT).as_posix(),'sha256':sha(electrical_path),'passed':sum(c['pass'] for c in E['checks']),'total':len(E['checks']),'failed_clause_names':[c['name'] for c in failed_electrical],'superseded_by_current_user_authorization':historical_clause,'replacement_current_proof_pass':revised_check,'note':'Raw former electrical method remains83/84 and is not presented as84/84. Only its exact historical digital-track geometry clause is superseded by measured current RF-exact/digital-endpoint/barrel/width-layer/copper-path/nonincreased-length proof. Any other failure aborts the current review.'}
 R={'ok':all(c['pass'] for c in checks),'stage':'V2_GEOMETRY_GND_INDEPENDENT_NATIVE_REVIEW','routing_geometry_review_complete':True,'checks':checks,'inputs':inputs,'boards':boards,'raw_historical_electrical_method_review':raw_review,'native_CAD_modified':False,'refill_performed':False,'physical_tests_performed':False,'remaining_physical_checks':E['remaining_physical_checks'],'method':'Native saved before/after geometry and independent electrical review. Bends counted only degree2 vertices of same net/layer/width, so merging collinear segments alone does not claim bend reduction. Filled ground polygons unfractured before physical copper/barrel connectivity proof. Raw old electrical method83/84 explicitly retained: its exact digital segment geometry clause is superseded solely by current user-authorized straightening, with independent current preservation proof; all other clauses are unchanged.'}
 out=OUT/'independent_final.json';out.write_text(json.dumps(R,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 lines=['# Независимый итоговый аудит ровности трассировки','',f'Проверок: {sum(c["pass"] for c in checks)}/{len(checks)}. Платы не изменялись; заполненные полигоны и новые дорожки проверены в сохранённых native-файлах.','', '| Плата | Сегменты до → после | Повороты до → после | Микросегменты <0,25 мм | Длина, мм | GND vias / перенесено |','|---|---:|---:|---:|---:|---:|']
 for n,b in boards.items():
  x,y=b['before'],b['after'];lines.append(f'| {n} | {x["segments"]} → {y["segments"]} | {x["turns"]} → {y["turns"]} | {x["micro_segments_under_0_25_mm"]} → {y["micro_segments_under_0_25_mm"]} | {x["length_mm"]:.2f} → {y["length_mm"]:.2f} | {y["gnd_vias"]} / {b["gnd_vias_moved"]} |')
 lines+=['','Повороты посчитаны в вершинах степени 2 одной цепи, слоя и ширины, а не по количеству отрезков. Слияние прямых участков само по себе не засчитывается как устранение поворота.','', 'Исходный прежний электрический метод дал 83/84: единственная непройденная историческая проверка требовала прежнюю геометрию SPI/RESET/RXEN отрезок в отрезок. Пользователь разрешил выпрямление этих линий. В текущем аудите вместо этого требования доказаны неизменность RF-геометрии и цифровых net/pad-связей, межслойных переходов, ширины и слоёв, полная связность новых дорожек и отсутствие увеличения длины. Остальные 83 условия сохранены без изменения; исходный 83/84 отчёт приложен как свидетельство и не объявляется 84/84.','', 'Проверены неизменность компонентов, полярностей, pad/net memberships, посадок, настроек, размеров, keepout и зон; число GND vias и размеры сверловки; сохранность RF и локальных возвратов; единая физическая GND-медь через plated barrels; штатные функции INA219, FakeTec GPIO, ISP и межплатное сопряжение. Свежий строгий KiCad DRC выполнен отдельно.','']
 failed=[c for c in checks if not c['pass']]
 if failed:lines+=['Нерешённые замечания:']+[f'- {c["name"]}: {json.dumps(c["detail"],ensure_ascii=False)}' for c in failed]
 else:lines+=['Замечаний, блокирующих сохранённую компоновку и связи, не найдено. Сеточные stitching vias отодвинуты из мешающих коридоров; RF и критичные локальные GND-return сохранены.']
 (OUT/'independent_final_RU.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
 print(json.dumps({'ok':R['ok'],'checks':len(checks),'passed':sum(c['pass'] for c in checks),'failed':[c['name'] for c in failed],'boards':{n:{'before':{key:b['before'][key] for key in ('segments','turns','length_mm','micro_segments_under_0_25_mm','gnd_vias')},'after':{key:b['after'][key] for key in ('segments','turns','length_mm','micro_segments_under_0_25_mm','gnd_vias')},'moved':b['gnd_vias_moved']} for n,b in boards.items()}},ensure_ascii=True))
 if failed:raise SystemExit(1)
if __name__=='__main__':main()
