import os
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('LB_OCR_HARDWARE')!='1',reason='set LB_OCR_HARDWARE=1 on the Pi with a USB webcam')


def test_real_capture_and_ocr(tmp_path):
    from level_bridge.ocr.camera import capture_image
    from level_bridge.ocr.processor import process_image
    path=capture_image(output_path=tmp_path)
    result=process_image(path)
    assert result['words'], 'Point camera at a clear printed English paragraph.'
