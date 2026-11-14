"""Heuristic mixed page layout: text rows plus automatically proposed equation crops.

This is not a general document understanding model. Blocks retain source boxes,
detector reasons and unresolved OCR so the user can review errors explicitly.
"""
import re
import time

from . import OCRError
from .preprocessing import decode_image
from .processor import get_engine, layout


def runs(flags):
    starts=[];start=None
    for index,value in enumerate([*flags,False]):
        if value and start is None:start=index
        if not value and start is not None:
            starts.append((start,index));start=None
    return starts


def page_columns(binary, vertical):
    """Use strong internal vertical rules when available; otherwise one column."""
    import cv2
    height,width=binary.shape
    found=[]
    for contour in cv2.findContours(vertical,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour)
        if .18*width<x<.82*width and h>.3*height and w<.04*width:
            found.append((x+w//2,y))
    separators=[]
    for x,y in sorted(found):
        if not separators or x-separators[-1][0]>width*.12:separators.append((x,y))
    if not separators:return [(0,0,width,height,0)]
    top=min(y for x,y in separators)
    regions=[]
    if top>height*.06:regions.append((0,0,width,top,-1))
    boundaries=[0]+[x for x,y in separators]+[width]
    for column,(left,right) in enumerate(zip(boundaries,boundaries[1:])):
        regions.append((left,top,right-left,height-top,column))
    return regions


def fraction_spans(binary, glyph_height):
    """Find complete numerator/bar/denominator stacks using separate ink components."""
    import cv2
    import numpy as np
    count,_,stats,_=cv2.connectedComponentsWithStats(binary)
    components=stats[1:]
    bars=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(6,round(glyph_height*.65)),1)))
    spans=[]
    for contour in cv2.findContours(bars,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour)
        if h>max(3,glyph_height*.2):continue
        overlapping=components[(components[:,0]<x+w)&(components[:,0]+components[:,2]>x)&(components[:,3]>3)]
        above=overlapping[(overlapping[:,1]+overlapping[:,3]<=y+1)&(y-overlapping[:,1]-overlapping[:,3]<glyph_height*1.1)]
        below=overlapping[(overlapping[:,1]>=y+h-1)&(overlapping[:,1]-y-h<glyph_height*1.1)]
        if len(above) and len(below):
            spans.append((x,int(above[:,1].min()),w,int((below[:,1]+below[:,3]).max())-int(above[:,1].min())))
    return spans


def row_boxes(binary, regions, glyph_height, fractions=()):
    import numpy as np
    boxes=[]
    gap=max(2,round(glyph_height*.32))
    for left,top,width,height,column in regions:
        segment=binary[top:top+height,left:left+width]
        active=np.count_nonzero(segment,axis=1)>=2
        for fx,fy,fw,fh in fractions:
            if fx>=left and fx+fw<=left+width:
                active[max(0,fy-top):min(height,fy+fh-top)]=True
        bands=runs(active)
        merged=[]
        for start,end in bands:
            if merged and start-merged[-1][1]<=gap:merged[-1]=(merged[-1][0],end)
            else:merged.append((start,end))
        for start,end in merged:
            ys,xs=np.nonzero(segment[start:end])
            if not len(xs):continue
            x1,x2=int(xs.min())+left,int(xs.max())+left+1
            if x2-x1<3 or end-start<3:continue
            boxes.append(dict(bbox=[x1,max(0,top+start-3),x2-x1,min(binary.shape[0],top+end+3)-max(0,top+start-3)],column=column))
    return boxes


_STOP={'an','the','is','in','on','to','by','of','as','if','or','and','for','it','be','we','he','no','so','use','let'}
_QUANTITIES={'speed','distance','time','density','mass','volume','pressure','force','area','resistance','voltage','current','power','work'}


def math_token(token):
    clean=re.sub(r'[^A-Za-z0-9=+×÷*/^²³√∑∫ρνΩαβΔ−<>.-]','',token).strip('.')
    if not clean:return False
    if clean.lower() in _STOP:return False
    letters=re.findall(r'[A-Za-z]+',clean)
    if any(len(part)>3 and part.lower() not in _QUANTITIES for part in letters):return False
    return (bool(re.search(r'[=+×÷*/^²³√∑∫ρνΩαβΔ−<>-]',clean)) or
            bool(re.fullmatch(r'[0-9.,]+|[A-Za-z]{1,3}',clean)) or clean.lower() in _QUANTITIES)


def equation_span(words):
    """Find an operator-centered math span without consuming surrounding prose."""
    anchors=[]
    for i,word in enumerate(words):
        token=word['text']
        if not re.search(r'[=+×÷/^²³√∑∫ρΩ−<>-]',token) or not math_token(token):continue
        if re.fullmatch(r'\d+[-−]',token):continue
        if token in ('-','−') and not (i>0 and i+1<len(words) and math_token(words[i-1]['text']) and math_token(words[i+1]['text'])):continue
        anchors.append(i)
    if not anchors:return None
    left,right=min(anchors),max(anchors)
    while left>0 and math_token(words[left-1]['text']):left-=1
    while right+1<len(words) and math_token(words[right+1]['text']):right+=1
    # Stop across real prose rather than merging unrelated inline expressions.
    if any(not math_token(w['text']) for w in words[left:right+1]):return None
    return left,right+1


def has_fraction(binary):
    import cv2
    height,width=binary.shape
    if height<10:return False
    bars=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(6,round(height*.25)),1)))
    for contour in cv2.findContours(bars,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,w,h=cv2.boundingRect(contour)
        if h>max(3,height*.16) or w>width*.85:continue
        if binary[max(0,y-height//2):y,x:x+w].any() and binary[y+h:min(height,y+h+height//2),x:x+w].any():return True
    return False


def detect_page(frame, options=None, engine=None):
    import cv2
    import numpy as np
    options=options or {};engine=engine or get_engine(options)
    height,width=frame.shape[:2]
    scale=max(1,min(3,1800/width,2600/height))
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    gray=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    h,w=binary.shape
    # Pale table rules can disappear at the darker text threshold.
    rule_binary=cv2.threshold(gray,220,255,cv2.THRESH_BINARY_INV)[1]
    vertical=cv2.morphologyEx(rule_binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(50,round(h*.15)))))
    horizontal=cv2.morphologyEx(rule_binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(70,round(w*.22)),1)))
    glyphs=[]
    for contour in cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        _,_,cw,ch=cv2.boundingRect(contour)
        if 4<ch<max(20,h*.15) and cw<w*.2:glyphs.append(ch)
    glyph_height=float(np.median(glyphs)) if glyphs else 20
    fractions=fraction_spans(binary,glyph_height)
    # Long fraction bars are mathematical content, not page/table dividers.
    for fx,fy,fw,fh in fractions:
        horizontal[max(0,fy-2):min(h,fy+fh+2),max(0,fx-2):min(w,fx+fw+2)]=0
    rule_mask=cv2.dilate(vertical|horizontal,None,iterations=1)>0
    cleaned=binary.copy();cleaned[rule_mask]=0
    ocr_gray=gray.copy();ocr_gray[rule_mask]=255
    regions=page_columns(cleaned,vertical)
    rows=row_boxes(cleaned,regions,glyph_height,fractions)
    if len(rows)>160:raise OCRError('Too many visual rows. Upload a clearer, smaller textbook region; no content was truncated.')
    blocks=[]
    for row_id,row in enumerate(rows):
        x,y,rw,rh=row['bbox'];crop=ocr_gray[y:y+rh,x:x+rw]
        data=engine.image_to_data(crop,lang='eng',config='--psm 7',output_type='dict',timeout=options.get('timeout_s',45))
        text,words=layout(data)
        text=text.replace('\n',' ')
        span=equation_span(words)
        fraction=has_fraction(cleaned[y:y+rh,x:x+rw])
        stacked=any(fx<x+rw and fx+fw>x and fy>=y and fy+fh<=y+rh for fx,fy,fw,fh in fractions)
        if stacked and not any(len(token)>3 and token.lower() not in _QUANTITIES for token in re.findall('[A-Za-z]+',text)):
            span=(0,len(words));fraction=True
        short_symbol=any(len(re.sub('[^A-Za-z0-9ρνΩαβΔ]','',word['text']))<=2 for word in words)
        if not span and fraction and (not words or (short_symbol and all(math_token(word['text']) for word in words))):
            span=(0,len(words))
        if not words and not fraction:
            # Preserve unrecognised visible ink instead of silently dropping it.
            text='[Unreadable region — compare with original]'
        parts=[]
        if span and span!=(0,len(words)):
            start,end=span
            mx=max(0,min(word['bbox'][0] for word in words[start:end])-4)
            mr=min(rw,max(word['bbox'][0]+word['bbox'][2] for word in words[start:end])+4)
            if start:parts.append(('text',' '.join(word['text'] for word in words[:start]),[x,y,mx,rh]))
            parts.append(('math',' '.join(word['text'] for word in words[start:end]),[x+mx,y,mr-mx,rh]))
            if end<len(words):parts.append(('text',' '.join(word['text'] for word in words[end:]),[x+mr,y,max(1,rw-mr),rh]))
        else:
            parts=[('math' if span else 'text',text,[x,y,rw,rh])]
        for kind,content,bbox in parts:
            blocks.append(dict(id=f'block_{len(blocks)}',kind=kind,text=content,bbox=bbox,column=row['column'],
                               row=row_id,reason='math symbols or fraction layout' if kind=='math' else 'text row',
                               ocr_confidence=min((word['confidence'] for word in words),default=0),
                               review_required=True))
    return dict(blocks=blocks,working_image=cv2.cvtColor(255-cleaned,cv2.COLOR_GRAY2BGR),scale=scale,
                width=w,height=h,columns=max((r[4] for r in regions),default=0)+1)


def extract_mixed(cfg,data,filename):
    from .math_ocr import recognize_crops
    options=cfg.app.get('ocr',{});started=time.perf_counter()
    frame=decode_image(data,filename,options.get('max_bytes',12*1024*1024),options.get('max_pixels',20_000_000))
    try:result=detect_page(frame,options)
    except Exception as exc:
        raise OCRError(f'Automatic text/layout detection failed: {exc}') from exc
    blocks=result['blocks']
    for block in blocks:block['bbox']=[round(value/result['scale'],2) for value in block['bbox']]
    math_blocks=[block for block in blocks if block['kind']=='math']
    max_regions=min(40,max(1,int(options.get('math',{}).get('max_regions',24))))
    warnings=['Automatic layout and equation recognition can miss or misclassify content. Review every block against the photo.']
    selected=math_blocks[:max_regions]
    timings={}
    if len(math_blocks)>max_regions:warnings.append(f'{len(math_blocks)-max_regions} equation regions exceed the per-page limit and remain unrecognised. Use a smaller page area.')
    if selected:
        try:
            # Detect on a cleaned copy, but recognise from original image pixels.
            # Thresholding can erase equals signs or turn Latin v into another glyph.
            padding=max(3,round(min(frame.shape[:2])*.012))
            crops=[]
            for block in selected:
                x,y,w,h=block['bbox']
                left=max(0,round(x-padding));top=max(0,round(y-padding))
                right=min(frame.shape[1],round(x+w+padding));bottom=min(frame.shape[0],round(y+h+padding))
                crops.append([left,top,right-left,bottom-top])
            predictions,timings=recognize_crops(cfg,frame,crops)
            if len(predictions)!=len(selected):raise OCRError('Math worker returned an incomplete batch.')
            for block,prediction in zip(selected,predictions):
                block.update(prediction)
        except OCRError as exc:
            warnings.append(str(exc))
    for block in math_blocks:
        if not block.get('latex'):block['error']=block.get('error','Equation not recognised; edit manually or use the crop tool.')
        else:
            raw=block['text'];latex=block['latex']
            compact=re.sub(r'\s+','',raw)
            simple=bool(re.fullmatch(r'[A-Za-z]=[A-Za-z]{1,3}',compact))
            visible=re.sub(r'\\[A-Za-z]+','',latex)
            visible=re.sub(r'[^A-Za-z=]','',visible)
            if ('=' in raw and '=' not in latex) or (simple and compact!=visible):
                block['warning']=f'Math draft differs from text OCR ({raw}). Compare the image; neither result is guaranteed correct.'
            if r'\begin{array}' in latex:
                block['warning']='This equation needs checking. The reader may have confused a symbol or the fraction layout.'
    lines=[]
    for row in sorted(set(block['row'] for block in blocks)):
        entries=[block for block in blocks if block['row']==row]
        lines.append(' '.join((f"${block['latex']}$" if block.get('latex') else block['text']) for block in entries))
    timings={key:value for key,value in timings.items() if key in ('backend','model_load_s','recognition_s')}
    return dict(blocks=blocks,combined_text='\n'.join(lines),warnings=warnings,review_required=True,
                width=frame.shape[1],height=frame.shape[0],columns=result['columns'],
                equation_candidates=len(math_blocks),recognised_equations=sum(bool(b.get('latex')) for b in math_blocks),
                duration_s=round(time.perf_counter()-started,3),**timings)
