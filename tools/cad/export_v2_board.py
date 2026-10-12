"""Exact native SVG/DRC/3D exports for one v2 board; no placement mutations."""
from pathlib import Path
import argparse, hashlib, json, subprocess
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pcb',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cli',type=Path,default=Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'))
    p.add_argument('--drc',action='store_true')
    p.add_argument('--mechanical',action='store_true',help='Standalone screen: run DRC without schematic parity')
    p.add_argument('--step',action='store_true')
    p.add_argument('--step-min-distance',default='0.01mm',help='KiCad STEP point-merging tolerance; reduce for small copper outlines')
    a=p.parse_args();pcb=a.pcb.resolve();out=a.out.resolve()
    if not pcb.is_relative_to(ROOT) or not out.is_relative_to(ROOT):raise ValueError('All v2 CAD paths must stay inside v2 workspace')
    out.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(pcb.read_bytes()).hexdigest()
    for view,layers,mirror in [('front','F.Cu,F.SilkS,Edge.Cuts',False),('back','B.Cu,B.SilkS,Edge.Cuts',True),('front_assembly','F.Fab,F.SilkS,Edge.Cuts',False),('back_assembly','B.Fab,B.SilkS,Edge.Cuts',True)]:
        dest=out/(pcb.stem+'_'+view+'.svg')
        subprocess.run([str(a.cli),'pcb','export','svg','--layers',layers,'--page-size-mode','2','--exclude-drawing-sheet','--mode-single',*(['--mirror'] if mirror else []),'-o',str(dest),str(pcb)],check=True)
    if a.drc:
        subprocess.run([str(a.cli),'pcb','drc','--format','json','--severity-all',*([] if a.mechanical else ['--schematic-parity']),'-o',str(out/(pcb.stem+'_drc.json')),str(pcb)],check=True)
    if a.step:
        command=[str(a.cli),'pcb','export','step','--force','--subst-models','--include-tracks','--include-zones','--min-distance',a.step_min_distance,'-o',str(out/(pcb.stem+'.step')),str(pcb)]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (out/(pcb.stem+'_step_export.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        print(result.stdout+result.stderr,flush=True)
        result.check_returncode()
    manifest={'pcb':str(pcb.relative_to(ROOT)),'sha256':digest,'artifacts':[{ 'path':str(x.relative_to(ROOT)), 'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(out.glob(pcb.stem+'*')) if x.is_file() and x.name!=pcb.stem+'_exports.json']}
    if a.step:
        manifest['step_options']={'minimum_point_distance':a.step_min_distance,'include_tracks':True,'include_zones':True}
        log=result.stdout+result.stderr
        manifest['step_export']={'exit_code':result.returncode,'wire_self_interference_warnings':log.count('Wire self-interference check failed'),'copper_fidelity_qualified':False,'log':str((out/(pcb.stem+'_step_export.log')).relative_to(ROOT))}
    (out/(pcb.stem+'_exports.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
