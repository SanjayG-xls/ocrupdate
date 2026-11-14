"""Offline Tesseract extraction with layout and candidate selection."""
from pathlib import Path
import os
import shutil
import time

from . import OCRError
from .preprocessing import decode_image, candidates
from .quality import candidate_score, image_warnings
from .verification import inspect_text


def layout(data):
    words, chunks = [], []
    previous = None
    for i, value in enumerate(data.get('text', [])):
        value = value.strip()
        if not value:
            continue
        line = tuple(int(data.get(k, [0]*len(data['text']))[i]) for k in ('page_num','block_num','par_num','line_num'))
        if previous is not None:
            chunks.append('\n\n' if line[:3] != previous[:3] else '\n' if line != previous else ' ')
        start = sum(map(len, chunks))
        chunks.append(value)
        words.append(dict(text=value, confidence=float(data['conf'][i]),
                          bbox=[int(data[k][i]) for k in ('left','top','width','height')],
                          line_id=list(line), paragraph_id=list(line[:3]), start=start, end=start+len(value)))
        previous = line
    return ''.join(chunks), words


def get_engine(options=None):
    options = options or {}
    import pytesseract as engine
    executable = options.get('tesseract_cmd') or shutil.which('tesseract')
    if not executable and os.name == 'nt':
        # Windows installers do not always add their directory to PATH.
        for folder in (Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Tesseract-OCR',
                       Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR'):
            candidate = folder / 'tesseract.exe'
            if candidate.is_file():
                executable = str(candidate)
                break
    if executable:
        engine.pytesseract.tesseract_cmd = str(executable)
    return engine

def process_image(path, options=None, engine=None):
    options = options or {}
    if engine is None:
        engine = get_engine(options)
    started = time.perf_counter()
    path = Path(path)
    frame = decode_image(path.read_bytes(), path.name, options.get('max_bytes', 12*1024*1024), options.get('max_pixels', 20_000_000))
    images, rotation = candidates(frame, options, engine)
    outputs = []
    try:
        for name, img in images:
            data = engine.image_to_data(img, lang='eng', config='--psm 3', output_type='dict', timeout=options.get('timeout_s', 45))
            text, words = layout(data)
            outputs.append((candidate_score(words), name, img, text, words))
    except Exception as exc:
        raise OCRError(f'OCR failed. Install Tesseract and English language data; check executable PATH. {exc}') from exc
    _, name, img, text, words = max(outputs, key=lambda entry: entry[0])
    report = inspect_text(text, words, options.get('confidence_threshold', 70))
    report['warnings'] += image_warnings(images[0][1])
    if not words:
        report['warnings'].append('No text detected. Retake or enter a passage manually after comparing the image.')
    return dict(original_image=str(path), extracted_text=text, words=words, **report,
                confidence_threshold=options.get('confidence_threshold', 70),
                candidate=name, rotation=rotation, coordinate_space='selected preprocessing candidate',
                width=img.shape[1], height=img.shape[0], ocr_duration_s=round(time.perf_counter()-started, 4))
