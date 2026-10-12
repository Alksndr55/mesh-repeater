"""Read-only POWER route proposal builder. Never saves a PCB.

Run with KiCad Python. Pad/via/width/branch anchors stay exact. Different
net native shapes require 0.205 mm clearance. Same-net new contacts are
rejected unless they meet an existing endpoint connection. Current source
SHA, all old UUIDs, and proposed paths are recorded for a separate editor.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/cad"))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()

PROTECTED_NETS = {
    "GND", "CS_P", "CHG_CS_M", "Net-(D1-K)", "Net-(D1-A)",
    "Net-(U1-VG)", "/GATE", "/2. Converter/LX1", "/2. Converter/LX2",
    "/2. Converter/FB_SYS", "/2. Converter/EN_UV",
    "Net-(U12-IN+)", "Net-(U12-IN-)",
}
KEEP = []
def uid(t): return str(t.m_Uuid.AsString())
def xy(p): return (round(k.ToMM(p.x), 6), round(k.ToMM(p.y), 6))
def vec(p): return k.VECTOR2I(k.FromMM(p[0]), k.FromMM(p[1]))
def point_segment_distance(p,a,z):
    dx,dy=z[0]-a[0],z[1]-a[1]
    if dx*dx+dy*dy < 1e-15:return math.dist(p,a)
    u=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.dist(p,(a[0]+u*dx,a[1]+u*dy))
def aligned(a,z):
    dx,dy=abs(z[0]-a[0]),abs(z[1]-a[1])
    return dx < 1e-6 or dy < 1e-6 or abs(dx-dy) < 1e-6
def options(a,z):
    dx,dy=z[0]-a[0],z[1]-a[1]; q=min(abs(dx),abs(dy))
    sx=1 if dx>=0 else -1; sy=1 if dy>=0 else -1
    raw=[[a,z]] if aligned(a,z) else []
    raw += [[a,(a[0],z[1]),z], [a,(z[0],a[1]),z],
            [a,(a[0]+sx*q,a[1]+sy*q),z],
            [a,(z[0]-sx*q,z[1]-sy*q),z]]
    out=[]
    for path in raw:
        path=[(round(p[0],6),round(p[1],6)) for p in path]
        clean=[path[0]]
        for p in path[1:]:
            if math.dist(p,clean[-1]) > 1e-6: clean.append(p)
        if clean not in out: out.append(clean)
    return out
def turns(path):
    angles=[math.degrees(math.atan2(z[1]-a[1],z[0]-a[0])) for a,z in zip(path,path[1:])]
    return sum(abs((z-a+180)%360-180)>.01 for a,z in zip(angles,angles[1:]))
def normalize(path):
    out=[]
    for p in path:
        if out and math.dist(p,out[-1]) < 1e-6: continue
        out.append(p)
        while len(out)>=3:
            a,c,z=out[-3:]
            ax,ay=c[0]-a[0],c[1]-a[1]; bx,by=z[0]-c[0],z[1]-c[1]
            if abs(ax*by-ay*bx) < 1e-7 and ax*bx+ay*by>0: out.pop(-2)
            else: break
    return out

def protected(t):
    net=t.GetNetname()
    if net in PROTECTED_NETS: return True
    a,z=xy(t.GetStart()),xy(t.GetEnd())
    box=(min(a[0],z[0]),min(a[1],z[1]),max(a[0],z[0]),max(a[1],z[1]))
    def overlaps(q): return box[0]<=q[2] and box[2]>=q[0] and box[1]<=q[3] and box[3]>=q[1]
    # INA pickup/force isolation: no changes to either shunt branch or input RC.
    if net in {"BAT","BAT_SYS"} and overlaps((44,2.8,61.7,16.6)): return True
    # Preserve the local TPS power loop and the CN3722 switched/sense loop.
    if net in {"BAT_SYS","SOLAR","/2. Converter/SYS_PRE"} and overlaps((36,14.7,50.2,25.8)): return True
    if t.GetLayer()==k.F_Cu and net in {"BAT_SYS","SOLAR"} and overlaps((8,18,35,43)): return True
    return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb")
    ap.add_argument("--out",default="audit/routing_geometry_2026_10_12/POWER_proposals.json")
    args=ap.parse_args(); source=Path(args.source)
    if not source.is_absolute(): source=ROOT/source
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    board=k.LoadBoard(str(source)); KEEP.append(board)
    all_tracks=list(board.GetTracks()); pads=[p for f in board.GetFootprints() for p in f.Pads()]
    items=all_tracks+pads
    shapes={}
    for item in items:
        for layer in [k.F_Cu,k.B_Cu]:
            if item.IsOnLayer(layer):
                s=item.GetEffectiveShape(layer);bb=s.BBox()
                shapes[(uid(item),layer)]=(s,(bb.GetX(),bb.GetY(),bb.GetRight(),bb.GetBottom()))
    # Pad, via, foreign same-net interior intersections, and retained copper are anchors.
    ts=[t for t in all_tracks if not isinstance(t,k.PCB_VIA) and not protected(t)]
    groups=defaultdict(list)
    for t in ts: groups[(t.GetNetCode(),t.GetLayer(),t.GetWidth())].append(t)
    proposals=[]
    for (net,layer,width),group in groups.items():
        graph=defaultdict(list)
        for t in group:
            a,z=xy(t.GetStart()),xy(t.GetEnd())
            graph[a].append((z,t));graph[z].append((a,t))
        group_ids={uid(t) for t in group}
        anchors={p for p,edges in graph.items() if len(edges)!=2}
        for p,edges in graph.items():
            point=vec(p);inc={uid(t) for _,t in edges}
            for item in items:
                if item.GetNetCode()!=net or not item.IsOnLayer(layer) or uid(item) in inc: continue
                s,bb=shapes[(uid(item),layer)]
                # Adjacent 0.1mm steps have overlapping round caps. Only a
                # centreline junction constitutes an extra track branch here.
                touch = (point_segment_distance(p,xy(item.GetStart()),xy(item.GetEnd()))<1e-6
                         if isinstance(item,k.PCB_TRACK) and not isinstance(item,k.PCB_VIA)
                         else s.Collide(point,0))
                if bb[0]<=point.x<=bb[2] and bb[1]<=point.y<=bb[3] and touch:
                    anchors.add(p); break
        visited=set()
        for start in sorted(anchors):
            for first_target,first in graph[start]:
                if uid(first) in visited: continue
                points=[start,first_target];chain=[first];visited.add(uid(first));prev=start;here=first_target
                while here not in anchors:
                    nxt=[(p,t) for p,t in graph[here] if uid(t)!=uid(chain[-1])]
                    if len(nxt)!=1 or uid(nxt[0][1]) in visited: break
                    target,t=nxt[0];chain.append(t);visited.add(uid(t));points.append(target);prev,here=here,target
                if len(chain)<3: continue
                chain_ids={uid(t) for t in chain}
                old_shapes=[shapes[(uid(t),layer)][0] for t in chain]
                fixed_endpoints=[vec(points[0]),vec(points[-1])]
                def clear(a,z):
                    margin=.55+k.ToMM(width)/2
                    if any(not(margin<=p[0]<=90-margin and margin<=p[1]<=60-margin) for p in [a,z]): return False
                    test=k.PCB_TRACK(board);test.SetStart(vec(a));test.SetEnd(vec(z));test.SetWidth(width);test.SetLayer(layer)
                    s=test.GetEffectiveShape(layer);bb=s.BBox();extra=k.FromMM(.205)
                    for item in items:
                        key=(uid(item),layer)
                        if uid(item) in chain_ids or key not in shapes: continue
                        other,box=shapes[key]
                        if bb.GetX()-extra>box[2] or bb.GetRight()+extra<box[0] or bb.GetY()-extra>box[3] or bb.GetBottom()+extra<box[1]: continue
                        if item.GetNetCode()!=net:
                            if s.Collide(other,extra): return False
                        elif s.Collide(other,0):
                            # Existing contacts at fixed endpoints may be retained; do not add a branch elsewhere.
                            if not any(other.Collide(p,0) for p in fixed_endpoints): return False
                    return True
                n=len(points);cost=[float("inf")]*n;choice=[None]*n;cost[-1]=0
                for i in range(n-2,-1,-1):
                    for j in range(i+1,n):
                        for cand in options(points[i],points[j]):
                            if not all(clear(a,z) for a,z in zip(cand,cand[1:])): continue
                            length=sum(math.dist(a,z) for a,z in zip(cand,cand[1:]))
                            score=length+.65*(len(cand)-1)+cost[j]
                            if score<cost[i]-1e-6:cost[i]=score;choice[i]=(j,cand)
                if choice[0] is None: continue
                out=[points[0]];i=0
                while i<n-1:
                    i,part=choice[i];out.extend(part[1:])
                out=normalize(out)
                before=sum(math.dist(a,z) for a,z in zip(points,points[1:]));after=sum(math.dist(a,z) for a,z in zip(out,out[1:]))
                if len(out)-1>=len(chain) or after>before+.001: continue
                proposals.append({"net":first.GetNetname(),"layer":board.GetLayerName(layer),"width_mm":k.ToMM(width),"old_UUIDs":[uid(t) for t in chain],"before_path_mm":points,"after_path_mm":out,"before_segments":len(chain),"after_segments":len(out)-1,"before_turns":turns(points),"after_turns":turns(out),"before_length_mm":before,"after_length_mm":after,"anchors_unchanged":True,"native_foreign_clearance_mm":.205})
    report={"stage":"READ_ONLY_POWER_GEOMETRY_PROPOSALS","CAD_modified":False,"source":str(source.relative_to(ROOT)).replace('\\','/'),"source_sha256":digest,"protected_nets":sorted(PROTECTED_NETS),"protected_track_UUIDs":[uid(t) for t in all_tracks if not isinstance(t,k.PCB_VIA) and protected(t)],"proposals":proposals,"counts":{"chains":len(proposals),"segments_removed":sum(c["before_segments"]-c["after_segments"] for c in proposals),"turns_removed":sum(c["before_turns"]-c["after_turns"] for c in proposals),"length_saved_mm":sum(c["before_length_mm"]-c["after_length_mm"] for c in proposals)},"limits":"Dry-run only; final set requires native DRC, pad connectivity, whole-plane and EMI review. Proposals are individually checked against the source board; mutual new-path collisions need sequential acceptance or joint DRC."}
    out=Path(args.out)
    if not out.is_absolute():out=ROOT/out
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    print(json.dumps(report["counts"]))
if __name__=="__main__":main()
