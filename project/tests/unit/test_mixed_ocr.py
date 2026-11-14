import copy
import io
from pathlib import Path
import pytest

cv2=pytest.importorskip('cv2')
np=pytest.importorskip('numpy')
from level_bridge.ocr import OCRError
from level_bridge.ocr.mixed import equation_span,page_columns,row_boxes,extract_mixed
from level_bridge.config import load_config


def words(text):return [{'text':token} for token in text.split()]


def test_inline_equation_keeps_surrounding_words():
    tokens=words('Use F = ma to calculate the force.')
    assert equation_span(tokens)==(1,4)
    assert equation_span(words('a = v - u'))==(0,5)
    assert equation_span(words('CLASS 9-')) is None
    assert equation_span(words('A well-known textbook question.')) is None


def test_two_column_rules_and_fraction_row_grouping():
    binary=np.zeros((600,600),np.uint8);vertical=binary.copy()
    vertical[120:550,299:302]=255
    regions=page_columns(binary,vertical)
    assert len(regions)==3 and regions[0][-1]==-1
    binary[160:170,20:60]=255;binary[173:180,20:60]=255
    binary[220:240,340:440]=255
    boxes=row_boxes(binary,regions,20)
    assert len(boxes)==2 and {box['column'] for box in boxes}=={0,1}


def test_fraction_stacks_are_two_complete_equations():
    from level_bridge.ocr.mixed import detect_page
    from types import SimpleNamespace
    path=Path(__file__).resolve().parents[1]/'fixtures'/'fraction_steps.png'
    def data(*a,**k):return dict(text=['x=1'],conf=[90],left=[0],top=[0],width=[10],height=[10])
    result=detect_page(cv2.imread(str(path)),engine=SimpleNamespace(image_to_data=data))
    blocks=result['blocks'];scale=result['scale']
    assert len(blocks)==2 and all(b['kind']=='math' for b in blocks)
    top=blocks[0]['bbox'];bottom=blocks[1]['bbox']
    assert top[1]/scale<7 and (top[1]+top[3])/scale>39
    assert bottom[1]/scale<69 and (bottom[1]+bottom[3])/scale>106


@pytest.fixture
def mixed_setup(monkeypatch):
    cfg=copy.deepcopy(load_config());cfg.app['ocr']['math']['enabled']=True
    image=cv2.imencode('.png',np.full((200,400,3),255,np.uint8))[1].tobytes()
    blocks=[dict(id='a',kind='text',text='Use the formula below.',bbox=[10,10,180,20],column=0,row=0),
            dict(id='b',kind='math',text='F=ma',bbox=[10,50,100,25],column=0,row=1),
            dict(id='c',kind='text',text='Find the force.',bbox=[10,95,140,20],column=0,row=2)]
    def detect(*a,**k):return dict(blocks=copy.deepcopy(blocks),scale=1,columns=1)
    monkeypatch.setattr('level_bridge.ocr.mixed.detect_page',detect)
    return cfg,image,blocks


def test_mixed_batch_preserves_text_and_original_coordinates(mixed_setup,monkeypatch):
    cfg,image,_=mixed_setup;calls=[]
    def recognize(cfg,frame,crops):
        calls.append((frame.shape,crops))
        return [{'latex':'F=ma'}],{'model_load_s':1,'recognition_s':.1,'review_required':True}
    monkeypatch.setattr('level_bridge.ocr.math_ocr.recognize_crops',recognize)
    result=extract_mixed(cfg,image,'question.png')
    assert result['combined_text']=='Use the formula below.\n$F=ma$\nFind the force.'
    assert len(calls)==1 and calls[0][0]==(200,400,3)
    assert result['blocks'][1]['bbox']==[10,50,100,25]
    assert result['review_required'] and result['recognised_equations']==1


def test_unavailable_model_retains_equation_region(mixed_setup,monkeypatch):
    cfg,image,_=mixed_setup
    def missing(*a,**k):raise OCRError('Model unavailable')
    monkeypatch.setattr('level_bridge.ocr.math_ocr.recognize_crops',missing)
    result=extract_mixed(cfg,image,'question.png')
    assert 'F=ma' in result['combined_text'] and result['recognised_equations']==0
    assert result['blocks'][1]['error'] and any('unavailable' in w for w in result['warnings'])


def test_model_disagreement_is_flagged(mixed_setup,monkeypatch):
    cfg,image,_=mixed_setup
    monkeypatch.setattr('level_bridge.ocr.math_ocr.recognize_crops',lambda *a:([{'latex':'P=mz'}],{}))
    result=extract_mixed(cfg,image,'question.png')
    assert 'differs' in result['blocks'][1]['warning']


def test_batch_uses_one_worker_and_cleans_temp_files(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    from level_bridge.ocr.math_ocr import recognize_crops
    executable=tmp_path/'python.exe';executable.touch()
    cfg=SimpleNamespace(root=tmp_path,path=lambda p:Path(p),app={'ocr':{'math':{'enabled':True,'python_path':str(executable)}}})
    commands=[]
    def worker(command,**kwargs):
        commands.append(command)
        manifest=Path(command[command.index('--manifest')+1])
        images=json.loads(manifest.read_text())
        assert len(images)==2 and all(Path(image).exists() for image in images)
        Path(command[command.index('--out')+1]).write_text(json.dumps({'predictions':[{'latex':'a=b'},{'latex':'c=d'}]}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('level_bridge.ocr.math_ocr.subprocess.run',worker)
    predictions,_=recognize_crops(cfg,np.full((200,400,3),255,np.uint8),[[10,10,80,30],[10,70,90,30]])
    assert len(commands)==1 and len(predictions)==2
    assert not Path(commands[0][commands[0].index('--manifest')+1]).exists()
