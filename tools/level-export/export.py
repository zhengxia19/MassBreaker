#!/usr/bin/env python3
"""Mass Breaker Tiled finite orthogonal tile layer -> V1 runtime JSON.
No third-party runtime dependency; explicit errors are never optimized away.
"""
import argparse
import json
import math
import re
from pathlib import Path

GRID_W, GRID_H, TILE_PX, CELL = 96, 160, 8, 0.25
CHAR_BY_LOCAL = {0: '.', 1: '1', 2: '2', 3: '3', 4: '#', 5: 'B'}
FLIP_MASK = 0xF0000000
THEMES = {'amber', 'coral', 'violet', 'azure', 'mint', 'gold'}

class LevelError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise LevelError(message)

def property_value(source, name, default=None):
    props = source.get('properties', [])
    for p in props:
        if p.get('name') == name:
            return p.get('value')
    return default

def validate_runtime(level, filename='<level>'):
    p = lambda ok,msg: require(ok, f'{filename}: {msg}')
    p(isinstance(level, dict), 'root must be object')
    p(level.get('schemaVersion') == 1, 'unsupported schemaVersion')
    level_id = level.get('id')
    p(isinstance(level_id,str) and re.fullmatch(r'L\d{3}',level_id) is not None, 'invalid ID')
    num=int(level_id[1:])
    p(1 <= num <= 30, 'V1 supports L001-L030')
    p(isinstance(level.get('title'),str) and 0 < len(level['title']) <= 100, 'title empty/long')
    p(type(level.get('chapter')) is int and level['chapter'] == (num-1)//5+1, 'chapter does not match ID')
    p(level.get('theme') in THEMES, 'invalid theme')
    p(level.get('world') in ({'width':24,'height':40},{'width':24.0,'height':40.0}), 'world must be 24x40')
    g=level.get('grid')
    p(isinstance(g,dict), 'missing grid')
    p(g.get('origin') == [0,0] and g.get('cellSize') == CELL and g.get('columns') == GRID_W, 'grid geometry incorrect')
    rows=g.get('rows')
    p(isinstance(rows,list) and len(rows) == GRID_H, 'must have 160 rows')
    counts={c:0 for c in CHAR_BY_LOCAL.values()}
    for y,row in enumerate(rows):
        p(isinstance(row,str) and len(row)==GRID_W,f'row {y} must be 96 characters')
        for x,c in enumerate(row):
            p(c in counts, f'unknown tile {c!r} at ({x},{y})')
            counts[c]+=1
            p(y < 114 or c == '.', f'control zone occupied at ({x},{y})')
    p(sum(counts[c] for c in '123B') > 0,'no breakable targets')
    spawn=level.get('spawn',{})
    p(isinstance(spawn,dict),'spawn missing')
    for name in ('ball','paddle'):
        coord=spawn.get(name)
        p(isinstance(coord,list) and len(coord)==2 and all(type(v) in (float,int) for v in coord),f'{name} requires [x,y]')
        x,y=coord
        p(0.17 <= x <= 23.83 and 0.17 <= y <= 39.83,f'{name} out of play area')
        cell=rows[int(y/.25)][int(x/.25)]
        p(cell == '.',f'{name} overlaps tile {cell}')
    ball=spawn['ball']; pad=spawn['paddle']
    p(abs(ball[0]-pad[0]) < 0.001 and abs(ball[1]-(pad[1]-0.35/2-0.17-0.005)) < 0.02,
      'initial ball must rest immediately above paddle')
    # Bounds on the whole paddle AABB and ball circle: no wall overlap in fixed bottom zone.
    p(2.25 <= pad[0] <= 21.75 and abs(pad[1]-38.0)<1e-5,'paddle marker not valid')
    # Bonus cells must have a non-wall approach side; gameplay still requires manual balance.
    for y,row in enumerate(rows):
        for x,c in enumerate(row):
            if c!='B':continue
            p(any(0 <= x+dx < GRID_W and 0 <= y+dy < GRID_H and rows[y+dy][x+dx]=='.'
                  for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))),
              f'bonus brick at ({x},{y}) has no exposed side')
    p(num>=5 or counts['B']==0, 'first bonus must appear in L005')
    p(num!=5 or counts['B']>=1, 'L005 must introduce bonus')
    return counts

def validate_layer_transform(layer, tag):
    """Reject Tiled visual/coordinate offsets that V1's grid schema cannot encode.

    Forbidding transforms (rather than silently dropping them) keeps the physics
    grid, markers and editor preview in one coordinate system.
    """
    name = layer.get('name', '<unnamed>')
    require(layer.get('type') != 'group',
            f'{tag}: group layers unsupported (nested offsets cannot be represented): {name}')
    for field in ('offsetx', 'offsety', 'x', 'y'):
        v = layer.get(field, 0)
        require(type(v) in (int, float) and math.isfinite(v),
                f'{tag}: layer {name} has invalid {field}={v!r}')
        require(v == 0, f'{tag}: layer {name} has unsupported {field}={v!r}; reset to 0 in Tiled')
    for field in ('parallaxx', 'parallaxy'):
        v = layer.get(field, 1)
        require(type(v) in (int, float) and math.isfinite(v) and v == 1,
                f'{tag}: layer {name} has unsupported {field}={v!r}; reset to 1 in Tiled')

def convert(path):
    src=json.loads(Path(path).read_text(encoding='utf-8'))
    tag=Path(path).name
    require(src.get('orientation')=='orthogonal' and src.get('infinite') is False,f'{tag}: finite orthogonal required')
    require((src.get('width'),src.get('height'),src.get('tilewidth'),src.get('tileheight'))==(GRID_W,GRID_H,TILE_PX,TILE_PX),
            f'{tag}: expected 96x160 with 8x8 source tiles')
    tilesets=src.get('tilesets')
    require(isinstance(tilesets,list) and len(tilesets)==1,f'{tag}: expected exactly one tileset')
    tile=tilesets[0]
    require(type(tile.get('firstgid')) is int and type(tile.get('tilecount')) is int and tile['tilecount']>=5,
            f'{tag}: tileset firstgid and tilecount invalid')
    first=tile['firstgid']
    layers=src.get('layers',[])
    require(isinstance(layers, list), f'{tag}: layers must be array')
    for layer in layers:
        require(isinstance(layer, dict), f'{tag}: layer must be object')
        validate_layer_transform(layer, tag)
    require(len([x for x in layers if x.get('name')=='bricks'])==1 and len([x for x in layers if x.get('name')=='markers'])==1,
            f'{tag}: exactly one bricks and markers layer required')
    bricks=next(x for x in layers if x.get('name')=='bricks')
    marker=next(x for x in layers if x.get('name')=='markers')
    require(bricks.get('type')=='tilelayer' and marker.get('type')=='objectgroup',f'{tag}: layer types invalid')
    # Tiled stores each finite tilelayer's own dimensions. Checking only map
    # width/height or the flattened data length would silently reinterpret
    # e.g. a 48x320 layer as 96x160 even though both have 15360 entries.
    lw, lh = bricks.get('width'), bricks.get('height')
    require(type(lw) is int and type(lh) is int and (lw, lh) == (GRID_W, GRID_H),
            f'{tag}: layer bricks must be {GRID_W}x{GRID_H}; got {lw!r}x{lh!r}')
    data=bricks.get('data')
    require(isinstance(data,list) and len(data)==GRID_W*GRID_H,f'{tag}: bricks must be uncompressed tile array')
    flat=[]
    for i,gid in enumerate(data):
        require(type(gid) is int and gid >= 0 and (gid & FLIP_MASK)==0,f'{tag}: invalid/flip gid at {i%GRID_W},{i//GRID_W}')
        local=0 if gid==0 else gid-first+1
        require(local in CHAR_BY_LOCAL,f'{tag}: unrecognized gid {gid} at {i%GRID_W},{i//GRID_W}')
        flat.append(CHAR_BY_LOCAL[local])
    rows=[''.join(flat[i*GRID_W:(i+1)*GRID_W]) for i in range(GRID_H)]
    objs=marker.get('objects',[])
    spawns={}
    for name,outname in (('ball_spawn','ball'),('paddle','paddle')):
        found=[o for o in objs if o.get('name')==name]
        require(len(found)==1 and found[0].get('point') is True,f'{tag}: point marker {name} missing or duplicate')
        obj=found[0]
        spawns[outname]=[round(float(obj['x'])/TILE_PX*CELL,6),round(float(obj['y'])/TILE_PX*CELL,6)]
    out={
        'schemaVersion':1,'id':property_value(src,'level_id'),
        'title':property_value(src,'title'),'chapter':property_value(src,'chapter'),
        'theme':property_value(src,'theme','amber'),
        'world':{'width':24,'height':40},
        'grid':{'origin':[0,0],'cellSize':CELL,'columns':GRID_W,'rows':rows},
        'spawn':spawns
    }
    validate_runtime(out,tag)
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    try:
        result=convert(args.input)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'Exported {result["id"]}: {args.output}')
    except (OSError,ValueError,KeyError,TypeError) as err:
        ap.exit(1,f'ERROR: {err}\n')
