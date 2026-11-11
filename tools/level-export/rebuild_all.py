#!/usr/bin/env python3
"""Regenerate all 30 runtime levels, manifest and previews from Tiled sources.
Requires Pillow only for preview generation; pure JSON steps use stdlib.
"""
import json,subprocess,sys
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
root=Path(__file__).resolve().parents[2]
spec=spec_from_file_location('mb_export',Path(__file__).with_name('export.py'))
mod=module_from_spec(spec);spec.loader.exec_module(mod)
from pathlib import Path
runtime=root/'assets/levels';source=root/'levels-src'; runtime.mkdir(parents=True,exist_ok=True)
for i in range(1,31):
    fid=f'L{i:03d}'
    dat=mod.convert(source/(fid+'.tmj'))
    (runtime/(fid+'.json')).write_text(json.dumps(dat,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(root/'examples/level_l001.json').write_text((runtime/'L001.json').read_text(encoding='utf8'),encoding='utf8')
script=Path(__file__).parent
for cmd in [
    [sys.executable,'-B',str(script/'validate.py'),'--dir',str(runtime),'--source',str(source)],
    [sys.executable,'-B',str(script/'geometry.py'),'--dir',str(runtime)],
    [sys.executable,'-B',str(script/'build_manifest.py'),'--dir',str(runtime),'--out',str(root/'design/levels/manifest.json')],
    [sys.executable,'-B',str(script/'render.py'),'--dir',str(runtime),'--out',str(root/'design/levels')]
]:subprocess.run(cmd,check=True)
print('SUCCESS: sources -> 30 JSON -> validated geometry -> manifest -> previews')
