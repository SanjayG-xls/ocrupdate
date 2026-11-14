"""Bounded decoding and optional OCR candidates; source bytes are preserved."""
import io

from . import OCRError


def decode_image(data, filename, max_bytes=12 * 1024 * 1024, max_pixels=20_000_000):
    from PIL import Image, UnidentifiedImageError
    import cv2
    import numpy as np
    from pathlib import Path
    if not data or len(data) > max_bytes:
        raise OCRError('Empty image or image exceeds the upload size limit.')
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.jpg', '.jpeg', '.png'):
        raise OCRError('Select a JPG or PNG image.')
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ('JPEG', 'PNG') or (im.format == 'PNG') != (suffix == '.png'):
                raise OCRError('Image format does not match its extension.')
            if im.width < 32 or im.height < 32 or im.width * im.height > max_pixels:
                raise OCRError('Image dimensions are outside the supported limits.')
            im.verify()
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise OCRError('Image cannot be decoded.')
        return frame
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise OCRError(f'Invalid image: {exc}') from exc


def candidates(frame, options=None, engine=None):
    import cv2
    options = options or {}
    rotation = 0
    if options.get('orientation', True) and engine is not None:
        try:
            osd = engine.image_to_osd(frame, output_type='dict', timeout=15)
            if float(osd.get('orientation_conf', 0)) >= 10:
                rotation = int(osd.get('rotate', 0))
                code = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(rotation)
                if code is not None:
                    frame = cv2.rotate(frame, code)
        except Exception:
            # OSD often cannot estimate orientation on a short paragraph.
            rotation = 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    result = [('gray', gray)]
    if options.get('contrast', True):
        result.append(('contrast', cv2.createCLAHE(2.0, (8, 8)).apply(gray)))
    if options.get('threshold', True):
        smooth = cv2.medianBlur(gray, 3)
        result.append(('threshold', cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]))
    if options.get('deskew', True):
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, .0174533, 80, minLineLength=gray.shape[1] // 5, maxLineGap=20)
        if lines is not None:
            import numpy as np
            angles = [np.degrees(np.arctan2(y2-y1, x2-x1)) for [[x1,y1,x2,y2]] in lines if abs(x2-x1) > 0]
            angles = [a for a in angles if abs(a) < 8]
            angle = float(np.median(angles)) if angles else 0
            if .5 < abs(angle) < 8:
                h, w = gray.shape
                matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
                result.append(('deskew', cv2.warpAffine(gray, matrix, (w,h), borderValue=255)))
    return result, rotation
