#!/usr/bin/env python3
"""Conservative structural reachability check based on immovable walls only.
Destructible cells are considered removable. NOT a proof of playability.
"""
import argparse,json,collections
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
spec=spec_from_file_location('mb_validate',Path(__file__).with_name('export.py'))
mod=module_from_spec(spec);spec.loader.exec_module(mod)
W,H=96,160;SW,SH=192,320;R=.17

def inspect(level):
    rows=level['grid']['rows']
    solid=[(x,y) for y in range(H) for x in range(W) if rows[y][x]=='#']
    blocked=bytearray(SW*SH)
    # Only 3x3 local tiles are necessary for R < cell size.
    for sy in range(SH):
        cy=(sy+.5)/8
        for sx in range(SW):
            cx=(sx+.5)/8;n=sy*SW+sx
            if cx < R or cx > 24-R or cy < R or cy > 40-R:
                blocked[n]=1;continue
            ix=int(cx*4);iy=int(cy*4)
            for ty in range(max(0,iy-1),min(H,iy+2)):
                for tx in range(max(0,ix-1),min(W,ix+2)):
                    if rows[ty][tx]!='#':continue
                    ax=max(tx*.25,min(cx,(tx+1)*.25))
                    ay=max(ty*.25,min(cy,(ty+1)*.25))
                    if (ax-cx)**2+(ay-cy)**2 < (R+1e-6)**2: blocked[n]=1;break
                if blocked[n]:break
    spawn=level['spawn']['ball'];start=int(spawn[1]*8)*SW+int(spawn[0]*8)
    if blocked[start]:return 0,1,['spawn inside inflated wall']
    seen=bytearray(SW*SH);seen[start]=1;q=collections.deque([start]);visited=0
    while q:
        n=q.popleft();visited+=1;y,x=divmod(n,SW)
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx=x+dx;ny=y+dy
            if 0<=nx<SW and 0<=ny<SH:
                j=ny*SW+nx
                if not blocked[j] and not seen[j]:seen[j]=1;q.append(j)
    missing=[]
    for y in range(H):
        for x,c in enumerate(rows[y]):
            if c not in '123B':continue
            can_hit=False
            for sy in range(max(0,2*y-2),min(SH,2*y+4)):
                py=(sy+.5)/8
                dpy=max(0,y*.25-py,py-(y+1)*.25)
                if dpy>R:continue
                for sx in range(max(0,2*x-2),min(SW,2*x+4)):
                    px=(sx+.5)/8
                    dpx=max(0,x*.25-px,px-(x+1)*.25)
                    if dpx*dpx+dpy*dpy <= R*R and seen[sy*SW+sx]:can_hit=True;break
                if can_hit:break
            if not can_hit:missing.append((x,y))
    return visited,len(missing),missing[:10]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dir',type=Path,required=True);a=p.parse_args()
    failures=[]
    for file in sorted(a.dir.glob('L[0-9][0-9][0-9].json')):
        l=json.loads(file.read_text(encoding='utf8')); reachable,missing,example=inspect(l)
        print(f'{file.stem}: reachable samples={reachable}, structurally unreachable targets={missing}')
        if missing:failures.append((file.stem,missing,example))
    if failures:raise SystemExit(f'FAIL: {failures}')
    print('OK: basic structural accessibility (destructible cells assumed removable; NOT a solvability proof)')
