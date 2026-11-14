"""Actual local Tesseract smoke test; no camera or model inference."""
import os
from pathlib import Path
import shutil
import textwrap

import pytest

pytest.importorskip('cv2')
pytest.importorskip('pytesseract')
Image = pytest.importorskip('PIL.Image')
from PIL import ImageDraw, ImageFont
from level_bridge.ocr.processor import process_image


def test_actual_printed_english_ocr(tmp_path):
    executable = shutil.which('tesseract')
    if os.name == 'nt' and not executable:
        for folder in (Path(os.environ.get('LOCALAPPDATA', ''))/'Programs'/'Tesseract-OCR',
                       Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Tesseract-OCR'):
            if (folder/'tesseract.exe').is_file():
                executable = str(folder/'tesseract.exe')
                break
    if not executable:
        pytest.skip('Tesseract executable unavailable; install system OCR engine')
    text = (Path(__file__).resolve().parents[2]/'data/passages/speed_passage.txt').read_text(encoding='utf-8')
    font_paths = ['C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    font_path = next((p for p in font_paths if Path(p).is_file()), None)
    if not font_path:
        pytest.skip('No scalable fixture font available')
    lines = textwrap.wrap(text, 85)
    image = Image.new('RGB', (1500, 100+45*len(lines)), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 28)
    for index, line in enumerate(lines):
        draw.text((50, 40+index*45), line, fill='black', font=font)
    path = tmp_path/'printed_speed.png'
    image.save(path)
    # Exercise automatic Windows discovery rather than supplying the found path.
    result = process_image(path, {'orientation': False, 'deskew': False})
    assert 'speed' in result['extracted_text'].lower()
    assert len(result['words']) > 100
    assert result['numeric_candidates'] and result['unit_candidates']
    assert result['ocr_duration_s'] > 0
