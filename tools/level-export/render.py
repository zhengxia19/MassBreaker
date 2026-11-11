#!/usr/bin/env python3
"""Generate design previews directly from runtime JSON. Requires Pillow (design tool only)."""
import argparse,json,math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
COLORS={'amber':'#F3BF4D','coral':'#F08A6D','violet':'#B99AF4','azure':'#54C6FF','mint':'#5CE8BA','gold':'#F5C76A'}
BG='#111B2C'; PALETTE={'1':None,'2':'#EA7891','3':'#E78F55','#':'#72829A','B':'#63EC92'}
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

def font(sz):
    try:return ImageFont.truetype(FONT,sz)
    except:return ImageFont.load_default()

def render(l):
    s=3
    W=96*s+24;H=160*s+50
    im=Image.new('RGB',(W,H),'#08101D');d=ImageDraw.Draw(im)
    title=l['id']+' '+l['title']
    d.text((13,6),title,fill='#DAEDFF',font=font(13))
    rows=l['grid']['rows'];palette=COLORS.get(l['theme'],'#F3BF4D')
    x0,y0=12,27
    d.rectangle((x0-2,y0-2,x0+96*s+2,y0+160*s+2),fill=BG)
    for y,row in enumerate(rows):
        for x,c in enumerate(row):
            if c=='.':continue
            color=palette if c=='1' else PALETTE[c]
            d.rectangle((x0+x*s,y0+y*s,x0+x*s+s-1,y0+y*s+s-1),fill=color)
    pad=l['spawn']['paddle']
    px=x0+pad[0]*4*s;py=y0+pad[1]*4*s
    d.rectangle((px-27,py-2,px+27,py+2),fill='#45D5F3')
    return im

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    all_items=[]
    for file in sorted(a.dir.glob('L[0-9][0-9][0-9].json')):
        obj=json.loads(file.read_text(encoding='utf8'));img=render(obj)
        img.save(a.out/(file.stem+'.png'))
        all_items.append(img)
    cols=5;rows=math.ceil(len(all_items)/cols)
    w=max(im.width for im in all_items);h=max(im.height for im in all_items)
    montage=Image.new('RGB',(cols*w,rows*h),'#08101D')
    for i,img in enumerate(all_items):montage.paste(img,((i%cols)*w,(i//cols)*h))
    montage.save(a.out/'all_30_levels.png')
    print('Render:',len(all_items),'previews + montage',montage.size)
