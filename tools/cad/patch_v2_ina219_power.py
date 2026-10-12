"""Local INA219 retrofit; preserve unrelated POWER native geometry.

Never rebuilds a board from the V1 baseline. Requires the parent-published
model and native schematic UUIDs; all net assignments come from that model.
"""
from pathlib import Path
import argparse, collections, hashlib, json, math, sys
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from complete_v2_routes import route, component_points, xy, vec
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_v2_routing_engineering import TraceGraph, uid

ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'design/MeshRepeater2_Power'
PCB=PROJECT/'MeshRepeater2_Power.kicad_pcb'
AUDIT=ROOT/'audit/ina219_and_vertical_2026_10_12/power_patch'
NEW=['U12','R71','R72','R73','C63','C64']
HELD=[]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def describe(t):
    if isinstance(t,k.PAD):return dict(uuid=uid(t),ref=t.GetParentFootprint().GetReference(),pin=t.GetNumber(),at=xy(t.GetPosition()),net=t.GetNetname())
    if isinstance(t,k.PCB_VIA):return dict(uuid=uid(t),net=t.GetNetname(),at=xy(t.GetPosition()),kind='via')
    return dict(uuid=uid(t),net=t.GetNetname(),start=xy(t.GetStart()),end=xy(t.GetEnd()),width=k.ToMM(t.GetWidth()),layer=k.LayerName(t.GetLayer()))

class Dinic:
    def __init__(self,n):self.edges=[[] for _ in range(n)]
    def add(self,u,v,c):
        a=[v,c,len(self.edges[v])];b=[u,0,len(self.edges[u])]
        self.edges[u].append(a);self.edges[v].append(b)
    def cut(self,s,t):
        total=0
        while True:
            level=[-1]*len(self.edges);level[s]=0;q=collections.deque([s])
            while q:
                u=q.popleft()
                for v,c,_ in self.edges[u]:
                    if c>1e-9 and level[v]<0:level[v]=level[u]+1;q.append(v)
            if level[t]<0:break
            it=[0]*len(self.edges)
            def dfs(u,f):
                if u==t:return f
                while it[u]<len(self.edges[u]):
                    e=self.edges[u][it[u]];v,c,r=e
                    if c>1e-9 and level[v]==level[u]+1:
                        x=dfs(v,min(f,c))
                        if x>1e-9:e[1]-=x;self.edges[v][r][1]+=x;return x
                    it[u]+=1
                return 0
            while True:
                x=dfs(s,1e9)
                if x<=1e-9:break
                total+=x
        seen={s};q=[s]
        while q:
            u=q.pop()
            for v,c,_ in self.edges[u]:
                if c>1e-9 and v not in seen:seen.add(v);q.append(v)
        return total,seen

def old_bat_partition(b,model,nets):
    """Cut the fewest native segments separating requested battery branches.

    This converts every surviving original segment to exactly one side; the
    new shunt is the only intended BAT/BAT_SYS connection. Unseeded fragments
    are removed. The later native DRC proves real copper-to-pad clearance.
    """
    b.BuildConnectivity();g=TraceGraph(b)
    items={u:t for u,t in g.items.items() if t.GetNetname()=='BAT'}
    keys=list(items);index={u:i for i,u in enumerate(keys)};s=2*len(keys);t=s+1
    flow=Dinic(t+1);raw=[];system=[]
    for u,item in items.items():
        i=index[u];cost=1e6 if isinstance(item,k.PAD) else 3 if isinstance(item,k.PCB_VIA) else 1+min(k.ToMM(item.GetLength()),20)/100
        flow.add(2*i,2*i+1,cost)
        if isinstance(item,k.PAD):
            ref=item.GetParentFootprint().GetReference();pin=item.GetNumber()
            wanted=model[ref]['nets'][pin]
            if wanted=='BAT':flow.add(s,2*i,1e6);raw.append(u)
            elif wanted=='BAT_SYS':flow.add(2*i+1,t,1e6);system.append(u)
            else:raise ValueError(('Unexpected old BAT reassignment',ref,pin,wanted))
        for other in g.edges[u]:
            if other in index:flow.add(2*i+1,2*index[other],1e6)
    cost,reach=flow.cut(s,t)
    if cost>=1e6:raise RuntimeError('Old raw/system copper cannot be separated without removing a pad')
    removed={u for u,i in index.items() if 2*i in reach and 2*i+1 not in reach}
    cut_desc=[describe(items[u]) for u in removed]
    for u in removed:b.Remove(items[u]);HELD.append(items[u])
    remaining=set(keys)-removed;components=[]
    while remaining:
        found={next(iter(remaining))};q=list(found)
        while q:
            u=q.pop()
            for other in g.edges[u]:
                if other in remaining and other not in found:found.add(other);q.append(other)
        remaining-=found
        rp=found&set(raw);sp=found&set(system)
        if rp and sp:raise RuntimeError('Raw and system still share original copper after cut')
        net='BAT' if rp else 'BAT_SYS' if sp else None
        if net:
            for u in found:items[u].SetNet(nets[net])
        else:
            for u in found:
                if isinstance(items[u],k.PAD):raise RuntimeError('Unassigned old battery pad')
                b.Remove(items[u]);HELD.append(items[u])
        components.append(dict(net=net,pads=[g.labels[u] for u in found if u in g.labels],item_count=len(found)))
    return dict(cut_cost=cost,removed=cut_desc,components=components)

def load_and_add():
    AUDIT.mkdir(parents=True,exist_ok=True)
    model=json.loads((PROJECT/'model.json').read_text(encoding='utf-8'))
    parts={p['ref']:p for p in model['parts']}
    assert set(NEW).issubset(parts),'MODEL_READY required'
    assert parts['U12']['nets']['7']=='INA_VIN_M','Unexpected sense orientation'
    before=sha(PCB);b=k.LoadBoard(str(PCB));HELD.append(b)
    nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
    needed={n for ref in NEW for n in parts[ref]['nets'].values() if n is not None}|{'BAT_SYS','SDA','SCL','SYS_3V3'}
    for name in sorted(needed-set(nets)):
        n=k.NETINFO_ITEM(b,name,max(x.GetNetCode() for x in nets.values())+1);b.Add(n);nets[name]=n
    fps={f.GetReference():f for f in b.GetFootprints()}
    if set(NEW)&set(fps):raise RuntimeError('New monitor footprints already present; do not rerun initial patch')
    (AUDIT/'before_power.kicad_pcb').write_bytes(PCB.read_bytes())
    partition=old_bat_partition(b,parts,nets)
    original_fields={ref:{field.GetName():field.GetText() for field in f.GetFields()} for ref,f in fps.items()}
    for ref in NEW:
        p=parts[ref];lib,name=p['footprint'].split(':',1)
        f=k.FootprintLoad(str(PROJECT/(lib+'.pretty')),name)
        if f is None:raise RuntimeError(('Missing local footprint',ref,name))
        f.SetReference(ref);f.SetValue(p['value']);f.SetFPID(k.LIB_ID(lib,name))
        b.Add(f)
        if p.get('native_layer','F.Cu')=='B.Cu':f.Flip(k.VECTOR2I(0,0),False)
        f.SetPosition(vec((p['x'],p['y'])));f.SetOrientationDegrees(p['rotation']);f.SetDNP(bool(p.get('dnp',False)))
        path=k.KIID_PATH()
        for key in (p['sheet_path']+'/'+p['schematic_uuid']).strip('/').split('/'):path.push_back(k.KIID(key))
        f.SetPath(path)
        f.Reference().SetVisible(False);f.Value().SetVisible(False)
        for key,val in p.get('schematic_fields',{}).items():
            if key not in ('Reference','Value','Footprint'):f.SetField(key,str(val))
        for field in f.GetFields():field.SetVisible(False)
        for pd in f.Pads():
            name=p['nets'].get(pd.GetNumber());pd.SetNet(nets[name]) if name is not None else pd.SetNetCode(0)
        fps[ref]=f
    # Preserve scoped legacy names such as Net-(U8-K) and converter LX aliases.
    # Only the three repurposed interboard lands get new supply/data nets.
    for pd in fps['J101'].Pads():
        if pd.GetNumber() in ('7','10','12'):pd.SetNet(nets[parts['J101']['nets'][pd.GetNumber()]])
    log=dict(input_sha256=before,partition=partition,new_footprint_poses={ref:{key:parts[ref].get(key) for key in ('x','y','rotation','native_layer')} for ref in NEW})
    return b,parts,nets,fps,log

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--inspect',action='store_true');ap.add_argument('--add-only',action='store_true');args=ap.parse_args()
    b,parts,nets,fps,log=load_and_add()
    if args.inspect:
        log['old_battery_items']=[describe(t) for t in b.GetTracks() if t.GetNetname() in ('BAT','BAT_SYS')]
        log['pads']=[describe(pd) for ref in NEW+['J8','J12','J101','R15','R47','C53','R1','U2'] for pd in fps[ref].Pads()]
        (AUDIT/'inspection.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(log,ensure_ascii=False));return
    k.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity();k.SaveBoard(str(PCB),b)
    log['after_sha256']=sha(PCB)
    (AUDIT/'initial_addition.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(log,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
