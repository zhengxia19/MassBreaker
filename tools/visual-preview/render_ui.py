#!/usr/bin/env python3
"""Generate reproducible UI visual references from the project's real runtime levels.
Design-only Pillow tool. Ball/item positions and HUD values are deliberately
illustrative and are NOT outputs of a running physics engine.
No font binaries are bundled or copied into outputs.
"""
from pathlib import Path
import json, math, os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'design/ui/final'
VIS=ROOT/'design/visual'
S=2
W,H=720,1600
VISUAL=json.loads((ROOT/'assets/config/visual.json').read_text(encoding='utf-8'))
C=VISUAL['colors']
BG=C['background']; PANEL=C['surface']; PANEL2=C['surfaceRaised']; TEXT=C['textPrimary']
SUB=C['textSecondary']; CYAN=C['cyan']; MINT=C['mint']; YELLOW=C['yellow']; RED=C['error']; PURPLE=C['bonus']
THEMES=VISUAL['themes']
FONT_PATH=os.environ.get('MB_UI_FONT')
if not FONT_PATH:
    candidates=['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf']
    FONT_PATH=next((candidate for candidate in candidates if Path(candidate).is_file()), None)
if not FONT_PATH:
    raise RuntimeError('Missing CJK design font; set MB_UI_FONT to a licensed local font path (no font file is bundled).')
fonts={n:ImageFont.truetype(FONT_PATH,int(n*S)) for n in [10,11,12,13,14,15,16,17,18,20,22,24,27,30,34,38]}

def f(n):
    if n not in fonts: fonts[n]=ImageFont.truetype(FONT_PATH,int(n*S))
    return fonts[n]
def xy(v):return round(v*S)
def box(d,bb,fill,rad=0,outline=None,width=1):
    bb=tuple(xy(v) for v in bb)
    d.rounded_rectangle(bb,radius=xy(rad),fill=fill,outline=outline,width=xy(width))
def text(d,pt,txt,size=14,color=TEXT,anchor='la'):
    d.text((xy(pt[0]),xy(pt[1])),str(txt),font=f(size),fill=color,anchor=anchor)
def line(d,pts,fill,width=1):d.line([(xy(x),xy(y)) for x,y in pts],fill=fill,width=xy(width))
def page():
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    for y in range(0,800,40):line(d,[(0,y),(360,y)],'#0b1828')
    return im,d

def header(d,name,subtitle=None,back=True):
    box(d,(12,14,348,80),PANEL,rad=12)
    if back:
        box(d,(22,24,68,70),PANEL2,rad=10);text(d,(45,46),'‹',27,anchor='mm')
        text(d,(84,39),name,20)
    else:text(d,(24,39),name,20)
    if subtitle:text(d,(24,64),subtitle,11,SUB)

def button(d,bb,label,kind='primary'):
    colors={'primary':('#216b89',CYAN),'secondary':(PANEL2,SUB),'danger':('#522b38',RED),'success':('#176a62',MINT),'selected':('#303f7a','#ddc8ff')}
    bg,stroke=colors[kind];box(d,bb,bg,rad=10,outline=stroke,width=1)
    x=(bb[0]+bb[2])/2;y=(bb[1]+bb[3])/2
    text(d,(x,y),label,16,TEXT if kind!='secondary' else SUB,anchor='mm')

def level_data(i):return json.loads((ROOT/f'assets/levels/L{i:03d}.json').read_text(encoding='utf-8'))

def draw_level(im,levelnum,bb=(0,94,360,694),ball_positions=None,item_positions=None):
    d=ImageDraw.Draw(im);x0,y0,x1,y1=bb
    box(d,bb,C['world'],rad=0)
    for gx in range(0,97,8):
        x=x0+(x1-x0)*gx/96;line(d,[(x,y0),(x,y1)],'#142333')
    for gy in range(0,161,8):
        y=y0+(y1-y0)*gy/160;line(d,[(x0,y),(x1,y)],'#142333')
    lev=level_data(levelnum);rows=lev['grid']['rows'];cw=(x1-x0)/96;ch=(y1-y0)/160
    fill=THEMES[lev['theme']]
    for gy,row in enumerate(rows):
        yy=y0+gy*ch
        for gx,c in enumerate(row):
            if c=='.':continue
            xx=x0+gx*cw
            bb2=(math.floor(xy(xx))+1,math.floor(xy(yy))+1,math.ceil(xy(xx+cw))-1,math.ceil(xy(yy+ch))-1)
            if bb2[2]<bb2[0] or bb2[3]<bb2[1]:continue
            if c=='#':co=C['wall']
            elif c=='1':co=fill
            elif c=='2':co=C['hp2']
            elif c=='3':co=C['hp3']
            elif c=='B':co=C['bonus']
            d.rectangle(bb2,fill=co)
            if c=='B':
                cx=(bb2[0]+bb2[2])/2;cy=(bb2[1]+bb2[3])/2
                d.point((cx,cy),fill='#ffffff')
            if c in '23':
                d.line((bb2[0]+1,bb2[1]+1,bb2[2]-1,bb2[1]+1),fill='#ffe3b3')
    # Deterministic illustrative ball positions (not simulated trajectory)
    if ball_positions is None:
        ball_positions=[(12,35)] if levelnum<5 else [(12,35),(18,24),(7,27),(20,15),(5,10),(10,16),(13,18),(17,12),(4,24),(15,31),(8,33),(11,13),(19,29),(16,9)]
    for j,(wx,wy) in enumerate(ball_positions):
        px=xy(x0+wx/24*(x1-x0));py=xy(y0+wy/40*(y1-y0));r=max(4,xy((x1-x0)/24*0.17))
        d.ellipse((px-r-5,py-r-5,px+r+5,py+r+5),fill=C['ballHalo'])
        d.ellipse((px-r,py-r,px+r,py+r),fill=C['ballCore'])
        d.ellipse((px-r//2,py-r//2,px+r//2,py+r//2),fill='#a8f6ff')
    if item_positions is None:item_positions=[]
    for wx,wy in item_positions:
        x=x0+wx/24*(x1-x0);y=y0+wy/40*(y1-y0)
        # 24x14 dp is a decorative billboard; hit box is separate 0.8x0.4 world units.
        box(d,(x-13,y-7,x+13,y+7),'#76338c',rad=4,outline='#dd8afe')
        text(d,(x,y),'+3',12,'#fff0ff',anchor='mm')
    # World paddle center y38, width4.5, height0.35
    px=x0+12/24*(x1-x0);py=y0+38/40*(y1-y0)
    ww=4.5/24*(x1-x0);hh=max(5,0.35/40*(y1-y0))
    box(d,(px-ww/2,py-hh/2,px+ww/2,py+hh/2),C['paddle'],rad=3,outline='#89edff')
    line(d,[(px-ww/2+4,py-hh/2+1),(px+ww/2-4,py-hh/2+1)],'#d9fbff',1)
    return lev

def hud(d,level,balls=3,remaining=2170,score='008200'):
    box(d,(12,10,348,84),PANEL,rad=10)
    text(d,(26,20),f'L{level:03d} · {level_data(level)["title"]}',16,TEXT)
    text(d,(26,57),'生命 3',13,SUB)
    text(d,(143,57),f'得分 {score}',13,YELLOW)
    box(d,(298,19,340,66),'#1a3550',rad=8)
    text(d,(319,41),'Ⅱ',22,CYAN,anchor='mm')
    box(d,(12,698,348,733),'#0d1d30',rad=7)
    text(d,(24,715),f'活动球 {balls}',13,MINT,anchor='lm')
    text(d,(336,715),f'目标 {remaining:,}',13,SUB,anchor='rm')
    box(d,(12,744,348,792),PANEL,rad=11)
    text(d,(180,768),'在此区域左右拖动控制挡板',13,SUB,anchor='mm')

def build_game(i,name,balls=None,remaining=None,score='008200',bonus=False):
    im,d=page(); l=draw_level(im,i,item_positions=[(13.2,34.1)] if bonus else [])
    if remaining is None:remaining=sum(ch in '123B' for row in l['grid']['rows'] for ch in row)
    hud(ImageDraw.Draw(im),i,balls if balls is not None else (14 if i>=5 else 3),remaining,score)
    im.save(OUT/name)
    return im

def overlay(im,heading,body,buttons):
    im=im.copy();dark=Image.new('RGB',im.size,'#030813');im=Image.blend(im,dark,0.63);d=ImageDraw.Draw(im)
    box(d,(28,218,332,582),PANEL,rad=18,outline='#314c6e')
    text(d,(180,270),heading,26,TEXT,anchor='mm')
    text(d,(180,316),body,13,SUB,anchor='mm')
    y=356
    for k,(lbl,kind) in enumerate(buttons):button(d,(60,y+k*66,300,y+52+k*66),lbl,kind)
    return im

def home():
    im,d=page();
    text(d,(180,104),'MASS',38,CYAN,anchor='mm');text(d,(180,154),'BREAKER',38,TEXT,anchor='mm')
    text(d,(180,194),'微型砖阵 · 连锁突破 · 道具多球',13,SUB,anchor='mm')
    preview=Image.new('RGB',(W,H),'#08111e');draw_level(preview,3,ball_positions=[(12,35)])
    im.paste(preview.crop((60,188,660,1258)).resize((560,320)),(80,465))
    d=ImageDraw.Draw(im);text(d,(180,414),'特色关卡：双腔体结构',17,TEXT,anchor='mm')
    button(d,(46,610,314,662),'开始游戏','primary');button(d,(46,673,314,725),'选择关卡','secondary');button(d,(46,736,314,786),'设置','secondary')
    return im

def select():
    im,d=page();header(d,'选择关卡','第一章 · 结构入门')
    box(d,(20,99,340,146),PANEL2,rad=8);text(d,(180,123),'‹   A 结构入门  1 / 6   ›',16,TEXT,anchor='mm')
    for k in range(5):
        col=k%2;row=k//2;x=20+col*165;y=166+row*184
        box(d,(x,y,x+155,y+169),PANEL,rad=12,outline='#233a55')
        thumb=Image.new('RGB',(240,400),'#08111e');draw_level(thumb,k+1,bb=(0,0,120,200),ball_positions=[])
        # crop actual created image: draw_level uses 0..120 x 0..200, avoid smearing
        c=thumb.crop((0,0,240,400)).resize((144*2,100*2))
        im.paste(c.crop((0,0,144*2,100*2)),(xy(x+5),xy(y+5)))
        d=ImageDraw.Draw(im);text(d,(x+14,y+118),f'L{k+1:03}',15,TEXT)
        text(d,(x+14,y+143),'★☆☆' if k==0 else '未通关',12,YELLOW if k==0 else SUB)
    return im

def settings():
    im,d=page();header(d,'设置','偏好保存在本机')
    for j,(n,active) in enumerate([('背景音乐',True),('游戏音效',True),('震动',False)]):
        y=124+74*j;box(d,(24,y,336,y+60),PANEL,rad=12);text(d,(44,y+30),n,16,TEXT,anchor='lm')
        box(d,(267,y+18,316,y+44), '#176b63' if active else '#3a465b',rad=15)
        x=300 if active else 283; d.ellipse((xy(x-9),xy(y+22),xy(x+9),xy(y+40)),fill=MINT if active else '#d6dce2')
    box(d,(24,390,336,480),PANEL,rad=12);text(d,(44,421),'关于游戏',17,TEXT);text(d,(44,453),'V1.3 设计参考 · 完全离线',13,SUB)
    return im

def tutorial():
    im,_=page();draw_level(im,5,item_positions=[(13.2,34.1)]);hud(ImageDraw.Draw(im),5,balls=4,remaining=800)
    im=overlay(im,'操作说明','保持弹球，接住 +3 获得额外球',[('单指滑动控制挡板','primary'),('轻点控制区发球','secondary'),('开始游戏','success')])
    return im

def card_sheet():
    im=Image.new('RGB',(1080,660),BG);d=ImageDraw.Draw(im)
    ft=lambda n:ImageFont.truetype(FONT_PATH,n)
    d.text((25,22),'微型砖块与游戏元素 · 标准视觉状态',font=ft(24),fill=TEXT)
    for k,(label,col) in enumerate([('普通砖 1HP','#d9a853'),('加固砖 2HP','#f5a25b'),('强化砖 3HP','#f47f9a'),('增球砖 B','#d878ef'),('固定墙','#73859a')]):
        x=30+210*k; y=100
        d.rounded_rectangle((x,y,x+125,y+125),radius=4,fill=col)
        if k==1:d.line((x+10,y+13,x+116,y+13),fill='#ffe3b3',width=6)
        if k==2:
            for h in [15,31,47]:d.line((x+10,y+h,x+116,y+h),fill='#ffced9',width=5)
        if k==3:d.ellipse((x+48,y+48,x+78,y+78),fill='white')
        if k==4:
            for yy in range(y+18,y+110,22):d.line((x+8,yy,x+115,yy),fill='#8f9fb0',width=3)
        d.text((x+62,259),label,font=ft(17),fill=SUB,anchor='mm')
    d.text((25,330),'弹球 · 挡板 · 掉落物（装饰尺寸不等于物理碰撞尺寸）',font=ft(22),fill=TEXT)
    d.ellipse((65,410,122,467),fill='#1d4e65');d.ellipse((76,420,110,454),fill='#d6f8ff')
    d.text((100,496),'球 Ø 0.34 世界单位',font=ft(16),fill=SUB,anchor='mm')
    d.rounded_rectangle((337,423,559,451),radius=12,fill='#0b84ab',outline='#98ecff',width=4)
    d.text((450,496),'挡板 4.5 × 0.35',font=ft(16),fill=SUB,anchor='mm')
    d.rounded_rectangle((731,408,850,456),radius=11,fill='#76338c',outline='#ebaeff',width=3)
    d.text((791,432),'+3',font=ft(26),fill='white',anchor='mm')
    d.text((791,496),'道具可视 1.6 × 0.9',font=ft(16),fill=SUB,anchor='mm')
    im.save(VIS/'component_states.png')

def build():
    OUT.mkdir(parents=True,exist_ok=True);VIS.mkdir(parents=True,exist_ok=True)
    build_game(3,'03_gameplay.png',balls=1,remaining=440,score='000000')
    build_game(28,'03_gameplay_multiball.png',balls=14,remaining=3890,score='056200',bonus=True)
    home().save(OUT/'01_home.png');select().save(OUT/'02_level_select.png')
    game=Image.open(OUT/'03_gameplay.png')
    overlay(game,'游戏暂停','物理和音效已暂停',[('继续游戏','primary'),('重新开始','secondary'),('返回选关','secondary')]).save(OUT/'04_pause.png')
    overlay(game,'关卡完成','★★★  得分 56,200',[('下一关','success'),('重玩本关','secondary'),('关卡选择','secondary')]).save(OUT/'05_win.png')
    overlay(game,'挑战失败','剩余生命 0 · 得分 14,200',[('重新挑战','primary'),('关卡选择','secondary')]).save(OUT/'06_lose.png')
    settings().save(OUT/'07_settings.png');tutorial().save(OUT/'08_tutorial.png')
    # single contact sheet containing all screens (models depict UI only)
    sheet=Image.new('RGB',(4*360,2*800),'#0c1827')
    names=['01_home','02_level_select','03_gameplay','04_pause','05_win','06_lose','07_settings','08_tutorial']
    for k,n in enumerate(names):
        small=Image.open(OUT/f'{n}.png').resize((360,800),Image.Resampling.LANCZOS)
        sheet.paste(small,((k%4)*360,(k//4)*800))
    sheet.save(OUT/'all_8_final_screens.png')
    card_sheet()
    (VIS/'README.md').write_text('''# 视觉规范图说明\n\n- `../ui/final/03_gameplay.png` 从当前 `assets/levels/L003.json` 绘制微砖与墙；球、得分、生命仅为设计示意，不是物理模拟输出。\n- `../ui/final/03_gameplay_multiball.png` 从 L028 真实地图绘制；+3 掉落物与小球位置为示意。\n- `component_states.png` 为放大后的颜色和形状状态稿，**不是直接用于游戏的最终 sprite 贴图**。\n- 所有 UI 原型图由 `tools/visual-preview/render_ui.py` 生成，使用本机已有字体绘制；字体二进制不在交付物中。运行时代码需依法接入有授权的字体。\n- 屏幕中的 96×160 地图来自运行时 JSON，避免继续沿用 V1.1 的连续色块旧示意。\n''',encoding='utf8')
    print('generated',len(list(OUT.glob('*.png'))),'screen PNGs and component palette sheet')
if __name__=='__main__':build()
