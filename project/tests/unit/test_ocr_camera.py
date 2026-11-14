from types import SimpleNamespace
import pytest
from level_bridge.ocr.camera import open_camera, capture_image
from level_bridge.ocr import OCRError


@pytest.mark.parametrize('opened,readable',[(False,False),(True,False),(True,True)])
def test_camera_release_on_all_paths(opened,readable):
    released=[]
    cap=SimpleNamespace(isOpened=lambda:opened,read=lambda:(readable,object() if readable else None),
                        set=lambda *a:False,release=lambda:released.append(True))
    cv=SimpleNamespace(VideoCapture=lambda *a:cap,CAP_V4L2=1,CAP_PROP_FRAME_WIDTH=3,CAP_PROP_FRAME_HEIGHT=4)
    if opened and readable:
        with open_camera(0,cv):pass
    else:
        with pytest.raises(OCRError,match='No usable webcam'):
            with open_camera(0,cv):pass
    assert released==[True]


def test_no_devices(monkeypatch):
    from level_bridge.ocr import camera
    monkeypatch.setattr(camera,'devices',lambda:[])
    with pytest.raises(OCRError):
        with camera.open_camera(cv=object()): pass


def test_capture_discards_startup_frames(monkeypatch, tmp_path):
    from level_bridge.ocr import camera
    ticks = iter([0, 0, .5, 1.5])
    monkeypatch.setattr(camera.time, 'monotonic', lambda: next(ticks))
    frames = iter(['dark startup', 'settling', 'ready'])
    released, encoded = [], []
    cap = SimpleNamespace(isOpened=lambda:True, read=lambda:(True,next(frames)),
                          set=lambda *a:True, release=lambda:released.append(True))
    def encode(extension, frame):
        encoded.append(frame)
        return True, SimpleNamespace(tobytes=lambda:b'jpeg bytes')
    cv = SimpleNamespace(VideoCapture=lambda *a:cap, CAP_V4L2=1,
                         CAP_PROP_FRAME_WIDTH=3,CAP_PROP_FRAME_HEIGHT=4,imencode=encode)
    path = capture_image(1, tmp_path, cv=cv)
    assert encoded == ['ready']
    assert path.read_bytes() == b'jpeg bytes'
    assert released == [True]


def test_disconnect_during_capture_releases_camera(monkeypatch, tmp_path):
    from level_bridge.ocr import camera
    monkeypatch.setattr(camera.time, 'monotonic', lambda:0)
    frames=iter([(True,'startup'),(False,None)])
    released=[]
    cap=SimpleNamespace(isOpened=lambda:True,read=lambda:next(frames),set=lambda *a:True,
                        release=lambda:released.append(True))
    cv=SimpleNamespace(VideoCapture=lambda *a:cap,CAP_V4L2=1,CAP_PROP_FRAME_WIDTH=3,CAP_PROP_FRAME_HEIGHT=4)
    with pytest.raises(OCRError,match='disconnected'):capture_image(1,tmp_path,cv=cv)
    assert released==[True] and not list(tmp_path.iterdir())
