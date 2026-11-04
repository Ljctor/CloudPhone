"""Passive owned-resource balances from reviewed real screen crops.

Companion stones use the shared balance row, never the skill-upgrade costs.
Dungeon feathers use their owned-count headers, never Enter or area buttons.
No route, tap, purchase or navigation permission is supplied by these readers.
The measured 480x1040 render is supported; other renders remain unread.
"""
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('slayer_resource_native', HERE / 'resource_native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
STONES_BALANCE_CALIBRATED = True
FEATHER_BALANCE_CALIBRATED = True
STONES = ('stone_red', 'stone_blue', 'stone_green', 'stone_yellow')
FEATHERS = ('feather_white', 'feather_green', 'feather_purple')
FIELDS = STONES + FEATHERS
# Font26 and the control's actual pixel phases, independent of any amount.
STONE_BOXES = ((100,262,158,283), (195,262,250,283), (286,262,343,283), (379,262,437,283))
STONE_ICONS = ((76,259,92,280), (170,259,187,280), (264,259,281,280), (358,259,375,280))
STONE_LEVELS = ((130,), (130,160), (100,110), (130,))
FEATHER_ICONS = {'feather_white': (392,181,419,204),
                 'feather_green': (392,175,419,200), 'feather_purple': (392,175,419,200)}


@lru_cache(maxsize=8)
def fixture(name):
    lines = [line for line in (HERE / 'fixtures' / (name + '.txt')).read_text().splitlines()
             if line and not line.startswith('#')]
    width,height,x,y,w,h = map(int, lines[0].split())
    raw = bytes.fromhex(''.join(lines[1:]))
    if len(raw) != w*h*3:
        raise ValueError('invalid resource calibration crop')
    return width,height,x,y,w,h,raw


def pixels(shot, box):
    width,_,raw = shot
    left,top,right,bottom = box
    return tuple(tuple(raw[(y*width+x)*3:(y*width+x)*3+3])
                 for y in range(top,bottom) for x in range(left,right))


def icon_colour(index, r,g,b):
    if index == 0:
        return r>100 and r>g*1.4 and r>b*1.3
    if index == 1:
        return b>100 and b>r*1.3 and b>g*1.1
    if index == 2:
        return g>95 and g>r*1.2 and b>r*1.2
    return r>100 and g>85 and r>b*1.3 and g>b*1.2


def stones_visible(shot):
    return all(sum(icon_colour(index,*rgb) for rgb in pixels(shot,box)) >= 15
               for index,box in enumerate(STONE_ICONS))


def stones(shot):
    if not STONES_BALANCE_CALIBRATED or shot[:2] != (480,1040) or not stones_visible(shot):
        return {}
    result = {}
    for index,(field,box,levels) in enumerate(zip(STONES,STONE_BOXES,STONE_LEVELS)):
        line = pixels(shot,box)
        width = box[2]-box[0]
        readings = []
        for level in levels:
            rows = tuple(tuple(int(min(rgb)>=level) for rgb in line[y*width:(y+1)*width])
                         for y in range(box[3]-box[1]))
            found = native.decode(rows,15.0 if index==2 else 14.75,0.0 if index==2 else .25)
            if found:
                readings.append(found)
        # Distinct plausible numeric paths at different raster thresholds
        # reject the field instead of choosing whichever balance looks likely.
        result[field] = readings[0] if readings and all(r==readings[0] for r in readings) else None
    return result


def title_matches(shot,field):
    _,_,left,top,width,height,reference = fixture('resource_' + field + '_title')
    expected = tuple(max(reference[i:i+3])>=180 for i in range(0,len(reference),3))
    if sum(expected)<40:
        return False
    actual = tuple(max(rgb)>=180 for rgb in pixels(shot,(left,top,left+width,top+height)))
    return sum(a!=b for a,b in zip(actual,expected))<=2


def feather_icon(shot,field):
    _,_,x,y,w,h,raw = fixture('resource_' + field)
    box = FEATHER_ICONS[field]
    expected = [raw[((cy-y)*w+cx-x)*3:((cy-y)*w+cx-x)*3+3]
                for cy in range(box[1],box[3]) for cx in range(box[0],box[2])]
    actual = pixels(shot,box)
    return sum(abs(a-b) for pixel,ref in zip(actual,expected) for a,b in zip(pixel,ref)) < len(expected)*3*8


def glyphs(shot):
    rows = [[min(rgb)>=200 for rgb in pixels(shot,(424,y,464,y+1))] for y in range(170,203)]
    columns = [any(row[x] for row in rows) for x in range(40)]
    spans,start = [],None
    for x,used in enumerate(columns+[False]):
        if used and start is None:
            start=x
        elif not used and start is not None:
            spans.append((start,x));start=None
    found=[]
    for left,right in spans:
        used=[y for y,row in enumerate(rows) if any(row[left:right])]
        found.append(tuple(''.join('#' if value else '.' for value in row[left:right])
                           for row in rows[min(used):max(used)+1]))
    return found


@lru_cache(maxsize=1)
def feather_digits():
    # Independently labelled individual glyphs, never whole known balances.
    data=json.loads((HERE/'resource_digit_shapes.json').read_text())
    bank={}
    for char,variants in data['glyphs'].items():
        for shape in variants:
            bank.setdefault(tuple(shape),set()).add(char)
    return bank


def feathers(shot):
    if not FEATHER_BALANCE_CALIBRATED or shot[:2]!=(480,1040):
        return {}
    fields=[field for field in FEATHERS if title_matches(shot,field) and feather_icon(shot,field)]
    if len(fields)!=1:
        return {}
    shapes=glyphs(shot)
    if not 1<=len(shapes)<=12:
        return {fields[0]:None}
    bank=feather_digits()
    choices=[bank.get(shape,set()) for shape in shapes]
    if any(len(chars)!=1 for chars in choices):
        return {fields[0]:None}
    text=''.join(next(iter(chars)) for chars in choices)
    if len(text)>1 and text.startswith('0'):
        return {fields[0]:None}
    return {fields[0]:{'text':text,'value':int(text)}}


def read(shot):
    return {**stones(shot),**feathers(shot)}
