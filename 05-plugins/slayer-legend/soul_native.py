"""Native Soul counters from independently extracted legacy-font digit rasters.

Only digits and comma at the measured atlas sizes are retained. The source
font, APK and rendering libraries are absent at runtime. The APK's legacy
UI.Text uses Bold, best fit, rounded advances and a half-size child transform.
Bilinear sampling retains the gray ink; hard thresholding loses glyph holes.
Spacing comes from font metrics, never from an expected balance.
"""
from collections import Counter
from functools import lru_cache
import math

NATIVE_DIGITS_CALIBRATED = True
MAX_LINE_ERROR = .0001
MIN_RELATIVE_MARGIN = .02
BOXES = {"green": (101,491,166,516), "blue": (194,491,260,516), "red": (288,491,353,516)}
# (width, height, left bearing, top bearing, advance, binary raster rows).
# AaSirius1 font, independent source glyphs; no observed amount enters these.
import importlib.util
import os
_spec=importlib.util.spec_from_file_location('slayer_legacy_font',os.path.join(os.path.dirname(__file__),'legacy_font.py'))
_font=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_font)
GLYPHS=_font.glyph_bank()
# The Text rectangle width259.81 atCanvas4/9:115.47source pixels.
MAX_ADVANCE=115.5
_raster=_font.raster
_screen=_font.screen


def _runs(row):
    spans = []
    for x, value in enumerate(row):
        if value:
            if spans and spans[-1][1] == x - 1:
                spans[-1] = (spans[-1][0], x)
            else:
                spans.append((x, x))
    return spans


def _prepare(rows):
    width, height = len(rows[0]), len(rows)
    marks = [[value > 200 for value in row] for row in rows]
    used = [y for y in range(height) if any(marks[y])]
    if not used:
        return None
    top, bottom = min(used), max(used)
    commas = _runs(marks[bottom])
    if len(commas) not in (2, 3) or not 5 <= bottom - top <= 11 or any(r-l > 2 for l,r in commas):
        return None
    first = min(x for y in range(top, bottom) for x, value in enumerate(marks[y]) if value)
    histogram = Counter(value for row in rows[top:bottom+1] for value in row)
    dark = [(count,value) for value,count in histogram.items() if value < 80]
    if not dark:
        return None
    background = max(dark)[1]
    foreground = max(histogram)
    if not 10 <= background <= 35 or foreground < 245:
        return None
    def loss(alpha):
        palette = [background + (foreground-background)*v for v in
                   (0,alpha/2,(1-alpha)/2,.5,alpha,1-alpha,(1+alpha)/2,1-alpha/2,1)]
        return sum(count * min(256,min((value-point)**2 for point in palette))
                   for value,count in histogram.items())
    alpha = min((loss(k/1000),k/1000) for k in range(5,496))[1]
    phases = ((.25-alpha/2) % .5, (.25+alpha/2) % .5)
    origins = sorted({first + delta + phase for delta in (-1.5,-1.,-.5,0.) for phase in phases})
    return width,height,top,bottom,commas,origins,background,foreground


def candidates(rows):
    """Blind grouped-number alternatives; repeated unchanged pixels are cheap."""
    return _candidates(tuple(tuple(row) for row in rows))


@lru_cache(maxsize=48)
def _candidates(rows):
    """No expected value or observed amount enters this decoder."""
    prepared = _prepare(rows)
    if not prepared:
        return []
    width,height,top,bottom,commas,origins,background,foreground = prepared
    observed = bytes(value for row in rows for value in row)
    lookup = bytes(background + round((foreground-background)*alpha/255) for alpha in range(256))
    @lru_cache(None)
    def patch(left,right):
        return bytes(observed[y*width+x] for y in range(height) for x in range(left,right))
    def solve(n,origin,baseline,exact):
        glyphs = GLYPHS[n]
        @lru_cache(None)
        def pattern(char,parity):
            advance = glyphs[char][4]
            left = math.ceil(origin+parity*.5-1.)
            right = math.ceil(origin+(parity+advance)*.5-1.)
            alpha = _raster(glyphs[char],origin,baseline,parity,left,right,height)
            centre = None
            if char == ',':
                used = [x for x,v in enumerate(alpha[bottom*(right-left):(bottom+1)*(right-left)]) if v>100]
                centre = (min(used)+max(used))/2 if used else (right-left-1)/2
            return alpha,right-left,centre
        @lru_cache(None)
        def composed(char,parity,previous):
            alpha,cells,centre=pattern(char,parity)
            if previous:
                left=math.ceil(origin+parity*.5-1.)
                prior=_raster(glyphs[previous],origin,baseline,parity-glyphs[previous][4],left,left+cells,height)
                alpha=_screen(prior,alpha)
            return alpha.translate(lookup),cells,centre
        @lru_cache(None)
        def cell(pen,char,previous):
            rendered,cells,centre = composed(char,pen%2,previous)
            left=math.ceil(origin+pen*.5-1.);right=left+cells
            if left<0 or right>width:
                return 1e12,None
            return math.dist(rendered,patch(left,right))**2,left+centre if centre is not None else None
        found=[]
        for leading in (1,2,3):
            roles = ['d']*leading
            for index in range(len(commas)):
                roles += [index]+['d']*3
            states = {(0,''):[(0.,'')]}
            for role in roles:
                following={}
                for (pen,previous),paths in states.items():
                    chars = ('123456789' if not previous else '0123456789') if role=='d' else ','
                    for char in chars:
                        npen=pen+glyphs[char][4]
                        if npen>118 or origin+npen*.5>width+1:
                            continue
                        score,centre = cell(pen,char,previous) if exact else cell(pen,char,'')
                        if char == ',' and abs(centre-sum(commas[role])/2)>1:
                            continue
                        key=(npen,char if exact else '*')
                        following.setdefault(key,[]).extend((cost+score,text+char) for cost,text in paths)
                states={key:sorted(set(paths))[:4 if exact else 2] for key,paths in following.items()}
                if not states:
                    break
            for (pen,_),paths in states.items():
                for score,text in paths:
                    if pen>MAX_ADVANCE or n+1 in GLYPHS and sum(GLYPHS[n+1][c][4] for c in text)<=MAX_ADVANCE:
                        continue
                    left=max(0,math.ceil(origin-1.));right=min(width,math.ceil(origin+pen*.5-1.))
                    outside=sum((observed[y*width+x]-background)**2 for y in range(height) for x in range(left))
                    if exact:
                        tail=_raster(glyphs[text[-1]],origin,baseline,pen-glyphs[text[-1]][4],right,width,height)
                        outside+=math.dist(tail.translate(lookup),patch(right,width))**2
                    else:
                        outside+=sum((observed[y*width+x]-background)**2 for y in range(height) for x in range(right,width))
                    found.append(((score+outside)/(width*height*255**2),text,n,origin,baseline))
        return found
    # A cheap glyph-only pass proposes poses; the second pass retains the
    # previous glyph, so overlap never becomes a guessed extra stroke.
    poses=[]
    for n,glyphs in GLYPHS.items():
        if n>22:
            continue
        if abs((glyphs['0'][1]-4)*.5-(bottom-top))>.75:
            continue
        for origin in origins:
            for baseline in (15.5,16.,16.5):
                coarse=solve(n,origin,baseline,False)
                if coarse:
                    poses.append(min(coarse))
    found=[]
    for _,_,n,origin,baseline in sorted(poses)[:4]:
        found.extend(solve(n,origin,baseline,True))
    if found and min(found)[0]>.0001:
        _,text,n,origin,baseline=min(found)
        refined=[]
        for pose in origins:
            if abs(pose-origin)>.5:
                continue
            for base in (15.5,16.,16.5):
                mask=bytes(width*height);pen=0
                for char in text:
                    mask=_screen(mask,_raster(GLYPHS[n][char],pose,base,pen,0,width,height))
                    pen+=GLYPHS[n][char][4]
                error=math.dist(mask.translate(lookup),observed)**2
                refined.append((error,pose,base))
        _,pose,base=min(refined)
        found.extend(solve(n,pose,base,True))
    best={}
    for row in found:
        if row[1] not in best or row[0]<best[row[1]][0]:
            best[row[1]]=row
    return tuple(sorted(best.values())[:8])


def decode(rows):
    if not rows or not rows[0] or any(len(row)!=len(rows[0]) for row in rows):
        return None
    alternatives=candidates(rows)
    if not alternatives:
        return None
    best=alternatives[0]
    if best[0]>MAX_LINE_ERROR or len(alternatives)<2 or alternatives[1][0]-best[0]<max(.0002,best[0]*MIN_RELATIVE_MARGIN):
        return None
    return best[1]


def read(shot,colour):
    if not NATIVE_DIGITS_CALIBRATED or shot[:2]!=(480,1040) or colour not in BOXES:
        return None
    width,_,pixels=shot
    left,top,right,bottom=BOXES[colour]
    rows=[[min(pixels[(y*width+x)*3:(y*width+x)*3+3]) for x in range(left,right)]
          for y in range(top,bottom)]
    text=decode(rows)
    return {"text":text,"value":int(text.replace(',','')),"step":1,"full":True} if text else None
