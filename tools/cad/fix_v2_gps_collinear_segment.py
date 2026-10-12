"""Apply the missed GPS_3V3 collinear join without changing physical copper."""
from pathlib import Path
import copy, hashlib, json, subprocess
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from sync_v2_native_metadata import parse

ROOT=Path(__file__).resolve().parents[2]
PCB=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
OUT=ROOT/'audit/routing_geometry_2026_10_12/gps_collinear_fix'
FIRST='0c84546c-9359-4e74-8f9e-b20b602408e2'
SECOND='b7df2a57-8716-48c6-9966-176ed1785108'
SOURCE='a509aeca65ab4d3f5cf8ac0295c9aafa62d046148040f22266fa7b4463ede427'
HELD=[]

def sha(data):return hashlib.sha256(data).hexdigest()
def uid(node):return next(n[1].strip('"') for n in node if isinstance(n,list) and n and n[0]=='uuid')
def segments(tree):return {uid(n):n for n in tree if isinstance(n,list) and n and n[0]=='segment'}
def without_segments(tree):return [n for n in tree if not(isinstance(n,list) and n and n[0]=='segment')]
def block(text,uuid):
    at=text.index('(uuid "'+uuid+'")')
    start=text.rfind('\n\t(segment',0,at)+1
    assert start>0
    depth=0
    for i in range(start,len(text)):
        if text[i]=='(':depth+=1
        elif text[i]==')':
            depth-=1
            if depth==0:return start,i+1,text[start:i+1]
    raise AssertionError('Unclosed segment')
def copper(items):
    poly=k.SHAPE_POLY_SET()
    for t in items:
        shape=k.SHAPE_POLY_SET()
        t.TransformShapeToPolygon(shape,k.F_Cu,0,1000,k.ERROR_OUTSIDE)
        shape.Unfracture();poly.BooleanAdd(shape)
    poly.Unfracture()
    return poly

def main():
    initial=PCB.read_bytes();assert sha(initial)==SOURCE,'Review this source before applying again'
    pro=PCB.with_suffix('.kicad_pro');project=pro.read_bytes()
    OUT.mkdir(parents=True,exist_ok=True)
    beforefile=OUT/'before_logic.kicad_pcb'
    if beforefile.exists():assert beforefile.read_bytes()==initial
    else:beforefile.write_bytes(initial)
    text=initial.decode('utf-8');tree=parse(text);old=segments(tree)
    expected=copy.deepcopy(old);del expected[SECOND]
    end=next(n for n in expected[FIRST] if isinstance(n,list) and n and n[0]=='end')
    assert end[1:]==['64.45','4.5'];end[1:]=['57.3','4.5']
    _,_,one=block(text,FIRST);_,_,two=block(text,SECOND)
    assert one.count('(end 64.45 4.5)')==1
    modified=text.replace(one,one.replace('(end 64.45 4.5)','(end 57.3 4.5)'),1).replace(two,'',1)
    aftertree=parse(modified)
    assert segments(aftertree)==expected
    assert without_segments(tree)==without_segments(aftertree)
    board=k.LoadBoard(str(PCB));HELD.append(board)
    oldnative={t.m_Uuid.AsString():t for t in board.GetTracks() if not isinstance(t,k.PCB_VIA)}
    a,b=oldnative[FIRST],oldnative[SECOND]
    assert a.GetNetname()==b.GetNetname()=='GPS_3V3'
    assert a.GetLayer()==b.GetLayer()==k.F_Cu and a.GetWidth()==b.GetWidth()==400000
    assert a.GetEnd()==b.GetStart()
    assert a.GetStart().y==a.GetEnd().y==b.GetEnd().y==4500000
    assert a.GetStart().x>a.GetEnd().x>b.GetEnd().x
    beforepoly=copper([a,b])
    try:
        assert PCB.read_bytes()==initial
        PCB.write_bytes(modified.encode('utf-8'))
        saved=k.LoadBoard(str(PCB));HELD.append(saved)
        tracks={t.m_Uuid.AsString():t for t in saved.GetTracks() if not isinstance(t,k.PCB_VIA)}
        assert SECOND not in tracks and len(tracks)==len(oldnative)-1
        afterpoly=copper([tracks[FIRST]])
        difference=k.SHAPE_POLY_SET();difference.BooleanSubtract(beforepoly,afterpoly);difference.Unfracture()
        reverse=k.SHAPE_POLY_SET();reverse.BooleanSubtract(afterpoly,beforepoly);reverse.Unfracture()
        area=(difference.Area()+reverse.Area())/1e12
        assert area<1e-9,('Copper union differs',area)
        drc=OUT/'LOGIC_strict_drc.json'
        run=subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--all-track-errors','--severity-all','--schematic-parity','--exit-code-violations','--format','json','-o',str(drc),str(PCB)],capture_output=True,text=True,encoding='utf-8',errors='replace')
        (OUT/'drc_console.txt').write_text(run.stdout+run.stderr,encoding='utf-8')
        data=json.loads(drc.read_text(encoding='utf-8'))
        counts={n:len(data.get(n,[])) for n in ('violations','unconnected_items','schematic_parity','ignored_checks')}
        assert run.returncode==0 and not any(counts.values()),counts
        assert pro.read_bytes()==project
        final=PCB.read_bytes();assert final==modified.encode('utf-8')
        result={'status':'APPLIED_GPS_COLLINEAR_JOIN','before_sha256':SOURCE,'after_sha256':sha(final),'retained_UUID':FIRST,'removed_UUID':SECOND,'net':'GPS_3V3','layer':'F.Cu','width_mm':.4,'path_mm':[[65.95,4.5],[57.3,4.5]],'physical_copper_symmetric_difference_mm2':area,'physical_copper_union_identical':True,'all_other_segments_and_all_nonsegment_tokens_unchanged':True,'project_bytes_unchanged':True,'saved_existing_fill_unchanged_no_refill_required':True,'segments_before':len(oldnative),'segments_after':len(tracks),'strict_DRC':counts,'strict_DRC_exit_code':run.returncode,'DRC':{'path':str(drc.relative_to(ROOT)).replace('\\','/'),'sha256':sha(drc.read_bytes())},'before_snapshot':str(beforefile.relative_to(ROOT)).replace('\\','/')}
        (OUT/'proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True),flush=True)
    except BaseException:
        PCB.write_bytes(initial)
        if pro.read_bytes()!=project:pro.write_bytes(project)
        raise

if __name__=='__main__':main()
