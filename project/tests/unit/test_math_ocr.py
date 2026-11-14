import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from level_bridge.ocr import OCRError
from level_bridge.ocr.math_ocr import validate_crop


@pytest.mark.parametrize('crop',[None,[],[0,0,1,1],[-1,0,20,20],[0,0,500,500],
                               [True,0,20,20],[0,0,float('nan'),20]])
def test_invalid_equation_crops(crop):
    with pytest.raises(OCRError):validate_crop(crop,100,100)


def test_valid_equation_crop():
    assert validate_crop([10,20,40,30],100,100)==(10,20,50,50)


def test_isolated_math_worker_and_cleanup(tmp_path,monkeypatch):
    cv2=pytest.importorskip('cv2')
    np=pytest.importorskip('numpy')
    from level_bridge.ocr.math_ocr import recognize_math
    executable=tmp_path/'python.exe';executable.touch()
    options={'math':{'enabled':True,'python_path':str(executable)}}
    cfg=SimpleNamespace(app={'ocr':options},root=tmp_path,path=lambda p:Path(p))
    image=cv2.imencode('.png',np.full((100,200,3),255,np.uint8))[1].tobytes()
    calls=[]
    def worker(command,**kwargs):
        calls.append((command,kwargs))
        output=Path(command[command.index('--out')+1])
        output.write_text(json.dumps({'latex':r'\rho=\frac{m}{V}','review_required':True}),encoding='utf-8')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('level_bridge.ocr.math_ocr.subprocess.run',worker)
    result=recognize_math(cfg,image,'x.png',[10,10,80,40])
    assert result['review_required'] and result['latex']==r'\rho=\frac{m}{V}'
    command,kwargs=calls[0]
    assert command[0]==str(executable) and not kwargs.get('shell')
    assert kwargs['env']['HF_HUB_OFFLINE']=='1'
    assert not Path(command[command.index('--image')+1]).exists()
    options['math']['enabled']=False
    with pytest.raises(OCRError,match='disabled'):recognize_math(cfg,image,'x.png',[10,10,80,40])
