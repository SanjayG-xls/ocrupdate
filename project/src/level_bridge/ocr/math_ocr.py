"""Optional isolated math OCR. Draft formulas never bypass passage/teacher gates."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from . import OCRError
from .preprocessing import decode_image


def validate_crop(crop, width, height):
    if not isinstance(crop,list) or len(crop)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in crop):
        raise OCRError('Select one equation by dragging a rectangle on the image.')
    x,y,w,h=crop
    if x<0 or y<0 or w<8 or h<8 or x+w>width+1 or y+h>height+1:
        raise OCRError('Crop must be inside the image and at least 8 × 8 pixels.')
    return (round(x),round(y),min(width,round(x+w)),min(height,round(y+h)))


def recognize_math(cfg,data,filename,crop):
    import cv2
    options=cfg.app.get('ocr',{})
    frame=decode_image(data,filename,options.get('max_bytes',12*1024*1024),options.get('max_pixels',20_000_000))
    height,width=frame.shape[:2]
    left,top,right,bottom=validate_crop(crop,width,height)
    predictions,timings=recognize_crops(cfg,frame,[[left,top,right-left,bottom-top]],single=True)
    result={**timings,**predictions[0]}
    if result.get('error'):raise OCRError('Math OCR failed: '+result['error'])
    result['crop']=[left,top,right-left,bottom-top]
    return result


def recognize_crops(cfg,frame,crops,single=False):
    """Load the isolated model once for a bounded batch of automatic regions."""
    import cv2
    if not 1<=len(crops)<=40:raise OCRError('Select a page with at most 40 equation regions.')
    height,width=frame.shape[:2]
    options=cfg.app.get('ocr',{})
    settings=options.get('math',{})
    if not settings.get('enabled',False):
        raise OCRError('Experimental math OCR is disabled in configuration.')
    executable=cfg.path(settings.get('python_path','.venv-math/Scripts/python.exe' if os.name=='nt' else '.venv-math/bin/python'))
    if not executable.is_file():
        raise OCRError('Math OCR environment is missing. See docs/MATH_OCR.md for separate desktop setup.')
    # Temporary crop/result are removed after success, error or timeout.
    with tempfile.TemporaryDirectory(prefix='level_bridge_math_') as temporary:
        paths=[]
        for index,crop in enumerate(crops):
            left,top,right,bottom=validate_crop(crop,width,height)
            image=Path(temporary)/f'equation_{index}.png'
            image.write_bytes(cv2.imencode('.png',frame[top:bottom,left:right])[1].tobytes())
            paths.append(str(image))
        output=Path(temporary)/'result.json'
        manifest=Path(temporary)/'images.json'
        manifest.write_text(json.dumps(paths),encoding='utf-8')
        env={**os.environ,'PYTHONUTF8':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
        try:
            completed=subprocess.run([str(executable),str(cfg.root/'scripts/math_ocr_worker.py'),
                                      *(['--image',paths[0]] if single else ['--manifest',str(manifest)]),'--out',str(output)],
                                     capture_output=True,text=True,encoding='utf-8',errors='replace',
                                     env=env,timeout=settings.get('timeout_s',120),
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as exc:
            raise OCRError('Math recognition timed out. Crop a single clear equation and retry.') from exc
        if not output.is_file():
            raise OCRError('Math OCR worker failed. Check the separate math environment installation.')
        result=json.loads(output.read_text(encoding='utf-8'))
        if completed.returncode or result.get('error'):
            raise OCRError('Math OCR failed: '+result.get('error','worker error'))
        predictions=result.pop('predictions',None)
        if predictions is None:
            predictions=[{'latex':result.pop('latex',''),'review_required':True}]
        return predictions,result
