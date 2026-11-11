#!/usr/bin/env python3
"""Refresh manifest and closed-design balance metrics from actual runtime levels."""
import json, argparse
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    prior=[]
    if a.out.exists():prior=json.loads(a.out.read_text(encoding='utf8'))
    byid={x['id']:x for x in prior}
    result=[]
    for file in sorted(a.dir.glob('L[0-9][0-9][0-9].json')):
        l=json.loads(file.read_text(encoding='utf8'))
        flat=''.join(l['grid']['rows'])
        name=byid.get(l['id'],{})
        b=flat.count('B')
        result.append(dict(id=l['id'],name=l['title'],cn=name.get('cn',l['title']),family=chr(ord('A')+l['chapter']-1),
            intent=name.get('intent',''),targets=sum(flat.count(x) for x in '123B'),wall=flat.count('#'),
            bonus=b,hp2=flat.count('2'),hp3=flat.count('3'),
            maxBallsIfEveryBonusCaught=1+3*b,variant=name.get('variant','')))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Updated manifest',len(result))
