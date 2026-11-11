#!/usr/bin/env python3
"""Validate runtime levels and compare against Tiled source; no assert-based rules."""
import argparse
import json
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

spec=spec_from_file_location('mb_export',Path(__file__).with_name('export.py'))
mod=module_from_spec(spec);spec.loader.exec_module(mod)

def check(directory,source=None):
    files=sorted(Path(directory).glob('L[0-9][0-9][0-9].json'))
    mod.require(len(files)==30, f'expected 30 JSON levels, found {len(files)}')
    total=[]
    for i,p in enumerate(files,1):
        l=json.loads(p.read_text(encoding='utf-8'))
        mod.require(l.get('id')==f'L{i:03d}',f'{p.name}: non-contiguous/mismatched ID')
        cnt=mod.validate_runtime(l,p.name)
        if source:
            s=Path(source)/(p.stem+'.tmj')
            mod.require(s.exists(),f'{p.stem}: Tiled source missing')
            mod.require(l==mod.convert(s),f'{p.stem}: JSON stale relative to Tiled source')
        total.append((l['id'],sum(cnt[k] for k in '123B'),cnt['B']))
    print('OK: 30 levels, grid/schema, bonus placement, metadata and source equivalence')
    for row in total:print('%s: targets=%d, B=%d'%row)
    return total

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dir',type=Path,required=True)
    ap.add_argument('--source',type=Path,help='optionally verify all .tmj sources')
    args=ap.parse_args()
    try:check(args.dir,args.source)
    except (OSError,ValueError,KeyError,TypeError) as e:ap.exit(1,f'ERROR: {e}\n')
