"""Independent read-only native-copper sampling for the two routing findings."""
from pathlib import Path
import argparse, hashlib, heapq, json, math, sys
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mm(n):return k.ToMM(n)
def xy(p):return [mm(p.x),mm(p.y)]
def uid(t):return str(t.m_Uuid.AsString())
def geometry(t):
 if isinstance(t,k.PCB_VIA):return {'uuid':uid(t),'net':t.GetNetname(),'type':'via','at':xy(t.GetPosition()),'diameter_mm':mm(t.GetWidth(k.F_Cu))}
 return {'uuid':uid(t),'net':t.GetNetname(),'type':'track','start':xy(t.GetStart()),'end':xy(t.GetEnd()),'layer':k.LayerName(t.GetLayer()),'width_mm':mm(t.GetWidth()),'length_mm':mm(t.GetLength())}
def ground(b,layer):
 result=k.SHAPE_POLY_SET()
 for z in b.Zones():
  if not z.GetIsRuleArea() and z.GetNetname()=='GND' and z.HasFilledPolysForLayer(layer):result.BooleanAdd(z.GetFilledPolysList(layer))
 for fp in b.GetFootprints():
  for p in fp.Pads():
   if p.GetNetname()=='GND' and p.IsOnLayer(layer):result.BooleanAdd(p.GetEffectivePolygon(layer))
 for t in b.GetTracks():
  if t.GetNetname()=='GND' and t.IsOnLayer(layer):
   ps=k.SHAPE_POLY_SET();t.TransformShapeToPolygon(ps,layer,0,1000,k.ERROR_OUTSIDE);result.BooleanAdd(ps)
 return result
def check(path,outname):
 before=sha(path); b=k.LoadBoard(str(path)); fps={f.GetReference():f for f in b.GetFootprints()}; tracks=list(b.GetTracks());gr={l:ground(b,l) for l in (k.F_Cu,k.B_Cu)}
 model=json.loads((ROOT/'design/MeshRepeater2_Logic/model.json').read_text(encoding='utf-8')); logical={}
 for part in model['parts']:
  for p in fps[part['ref']].Pads():
   if p.GetNumber() in part['nets']:logical[p.GetNetCode()]=part['nets'][p.GetNumber()]
 nets={name:{'segment_sum_mm':0,'via_count':0,'opposite_GND_uncovered_estimate_mm':0,'longest_missing_span_mm':0,'segments':[],'vias':[],'missing_spans':[],'lateral_ground_distances_mm':[],'worst_lateral_ground':None} for name in ('MOSI_RF','MISO_MCU','RADIO_RST','RADIO_RXEN','ANT_RF','ANT_SMA')}
 for t in tracks:
  name=logical.get(t.GetNetCode(),t.GetNetname())
  if name not in nets:continue
  n=nets[name];desc=geometry(t);desc['logical_net']=name
  if isinstance(t,k.PCB_VIA):n['via_count']+=1;n['vias'].append(desc);continue
  n['segment_sum_mm']+=mm(t.GetLength());n['segments'].append(desc)
  count=max(1,math.ceil(mm(t.GetLength())/.025));a,e=t.GetStart(),t.GetEnd();layer=k.B_Cu if t.GetLayer()==k.F_Cu else k.F_Cu; spans=[];missing=0
  for i in range(count+1):
   p=k.VECTOR2I(round(a.x+(e.x-a.x)*i/count),round(a.y+(e.y-a.y)*i/count))
   if not gr[layer].Contains(p):
    missing+=1
    lateral=mm(gr[t.GetLayer()].Distance(p))
    n['lateral_ground_distances_mm'].append(lateral)
    if n['worst_lateral_ground'] is None or lateral>n['worst_lateral_ground']['distance_mm']:
     n['worst_lateral_ground']={'uuid':uid(t),'layer':k.LayerName(t.GetLayer()),'at':xy(p),'distance_mm':lateral}
    if spans and spans[-1][1]==i-1:spans[-1][1]=i
    else:spans.append([i,i])
  n['opposite_GND_uncovered_estimate_mm']+=mm(t.GetLength())*missing/(count+1)
  for start,end in spans:
   length=mm(t.GetLength())*(end-start)/count
   gap={'uuid':uid(t),'layer':k.LayerName(layer),'length_mm':length,'start':[mm(a.x+(e.x-a.x)*start/count),mm(a.y+(e.y-a.y)*start/count)],'end':[mm(a.x+(e.x-a.x)*end/count),mm(a.y+(e.y-a.y)*end/count)]}
   n['missing_spans'].append(gap);n['longest_missing_span_mm']=max(n['longest_missing_span_mm'],length)
 for n in nets.values():
  values=sorted(n.pop('lateral_ground_distances_mm'))
  n['lateral_ground_on_uncovered_samples_mm']={'sample_count':len(values),'median':values[len(values)//2] if values else None,'p95':values[int(.95*(len(values)-1))] if values else None,'maximum':values[-1] if values else None}
 # Item-graph reference path is a consistent comparison with the prior audit;
 # summing whole segments is not an exact clipped pad-centre flight length.
 objects={uid(t):t for t in tracks}
 for f in fps.values():
  for p in f.Pads():objects[uid(p)]=p
 edges=defaultdict(set);conn=b.GetConnectivity()
 for u,t in objects.items():
  for other in list(conn.GetConnectedPads(t))+list(conn.GetConnectedTracks(t)):
   v=uid(other)
   if v in objects and t.GetNetCode()==other.GetNetCode():edges[u].add(v);edges[v].add(u)
 def selected(start,end):
  src=[uid(p) for p in fps[start[0]].Pads() if p.GetNumber()==start[1]]; dst={uid(p) for p in fps[end[0]].Pads() if p.GetNumber()==end[1]}
  def weight(u):
   t=objects[u]
   return mm(t.GetLength()) if isinstance(t,k.PCB_TRACK) and not isinstance(t,k.PCB_VIA) else mm(b.GetDesignSettings().GetBoardThickness()) if isinstance(t,k.PCB_VIA) else 0
  q=[(0,u) for u in src];d={u:0 for u in src};previous={};finish=None
  while q:
   cost,u=heapq.heappop(q)
   if cost!=d[u]:continue
   if u in dst:finish=u;break
   for v in edges[u]:
    candidate=cost+(weight(u)+weight(v))/2
    if candidate<d.get(v,math.inf):d[v]=candidate;previous[v]=u;heapq.heappush(q,(candidate,v))
  if finish is None:return {'connected':False}
  items=[finish]
  while items[-1] in previous:items.append(previous[items[-1]])
  items.reverse();trace=[objects[u] for u in items if isinstance(objects[u],k.PCB_TRACK) and not isinstance(objects[u],k.PCB_VIA)];vias=[objects[u] for u in items if isinstance(objects[u],k.PCB_VIA)]
  returns=[t for t in tracks if isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND']
  returns += [p for f in fps.values() for p in f.Pads() if p.GetNetname()=='GND' and p.GetAttribute()==k.PAD_ATTRIB_PTH]
  return {'connected':True,'whole_selected_segments_sum_mm':sum(mm(t.GetLength()) for t in trace),'via_count':len(vias),'tracks':list(map(geometry,trace)),'via_return_distances':[{'signal':xy(v.GetPosition()),'nearest_GND_barrel_mm':min(math.dist(xy(v.GetPosition()),xy(g.GetPosition())) for g in returns)} for v in vias]}
 pairs={'MOSI':(('R24','2'),('M2','14')),'MISO':(('R26','2'),('M1','6')),'RESET':(('M1','1'),('M2','4')),'MCU_power':(('J11','2'),('M1','9')),'MODEM_power_branch':(('J11','2'),('FB1','1')),'BAT_sense':(('J201','9'),('R27','1'))}
 zones=[]
 for z in b.Zones():
  if z.GetIsRuleArea():
   bounds=z.Outline().BBox()
   zones.append({'name':z.GetZoneName(),'uuid':uid(z),'tracks_forbidden':z.GetDoNotAllowTracks(),'vias_forbidden':z.GetDoNotAllowVias(),'copper_pour_forbidden':z.GetDoNotAllowZoneFills(),'layers':[k.LayerName(l) for l in (k.F_Cu,k.B_Cu) if z.IsOnLayer(l)],'bbox_mm':[mm(bounds.GetLeft()),mm(bounds.GetTop()),mm(bounds.GetRight()),mm(bounds.GetBottom())]})
 protected={name:{'pose':[mm(fps[name].GetPosition().x),mm(fps[name].GetPosition().y),fps[name].GetOrientationDegrees()],'pads':{p.GetNumber():logical.get(p.GetNetCode(),p.GetNetname()) for p in fps[name].Pads()},'native_pad_netnames':{p.GetNumber():p.GetNetname() for p in fps[name].Pads()}} for name in ('J10','M1','M2','J11','J201','R27')}
 result={'input':str(path.relative_to(ROOT)),'sha256':before,'method':'saved native copper; union of actual GND fill, tracks, pads and vias; independent 0.025mm opposite-layer axis sampling; exact whole-net segment sums; selected item graph sums are NOT pad-clipped electrical flight lengths','nets':nets,'selected_paths':{name:selected(*pair) for name,pair in pairs.items()},'rule_areas':zones,'protected':protected,'native_unchanged_by_review':sha(path)==before}
 assert result['native_unchanged_by_review'];(OUT/outname).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'sha256':before,'nets':{name:{key:n[key] for key in ('segment_sum_mm','via_count','opposite_GND_uncovered_estimate_mm','longest_missing_span_mm')} for name,n in nets.items()},'paths':{name:{k:v[k] for k in ('connected','whole_selected_segments_sum_mm','via_count') if k in v} for name,v in result['selected_paths'].items()},'rule_areas':zones},ensure_ascii=False))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--board',default='design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb');ap.add_argument('--out',default='reviewer_routing.json');args=ap.parse_args();check(ROOT/args.board,args.out)
