"""Backend-owned USB camera, with injectable OpenCV for hardware-free tests."""
from contextlib import contextmanager
from pathlib import Path
import platform
import time
import uuid

from . import OCRError


def devices():
    if platform.system() == "Linux":
        return [str(p) for p in sorted(Path('/dev').glob('video*'))]
    return list(range(4))


@contextmanager
def open_camera(camera_index=None, cv=None):
    if cv is None:
        import cv2 as cv
    for index in ([camera_index] if camera_index is not None else devices()):
        cap = cv.VideoCapture(index, cv.CAP_V4L2) if platform.system() == 'Linux' else cv.VideoCapture(index)
        try:
            if not cap.isOpened():
                continue
            cap.set(cv.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, 1080)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            yield cap, frame
            return
        finally:
            cap.release()
    raise OCRError('No usable webcam. Check USB connection, V4L2 permissions and other camera applications; upload an image instead.')


def capture_image(camera_index=None, output_path=None, cv=None, warmup_s=1.5):
    if cv is None:
        import cv2 as cv
    destination = Path(output_path or 'data/ocr/captures')
    folder = destination.parent if destination.suffix else destination
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'scan_{uuid.uuid4().hex}.jpg'
    with open_camera(camera_index, cv) as (cap, frame):
        # Opening a camera resets its exposure on many USB devices. Discard
        # startup frames instead of saving the first (often dark) frame.
        deadline = time.monotonic() + max(0, min(float(warmup_s), 5))
        for _ in range(150):
            if time.monotonic() >= deadline:
                break
            ok, frame = cap.read()
            if not ok or frame is None:
                raise OCRError('Webcam disconnected while preparing capture. Reconnect it or upload an image.')
        ok, data = cv.imencode('.jpg', frame)
        if not ok:
            raise OCRError('Camera image could not be encoded.')
        with path.open('xb') as stream:
            stream.write(data.tobytes())
    return path


def preview(camera_index=None):
    import cv2
    with open_camera(camera_index) as (cap, frame):
        while True:
            ok, encoded = cv2.imencode('.jpg', frame)
            if not ok:
                raise OCRError('Camera preview encoding failed.')
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + encoded.tobytes() + b'\r\n'
            ok, frame = cap.read()
            if not ok:
                raise OCRError('Webcam disconnected during preview.')
