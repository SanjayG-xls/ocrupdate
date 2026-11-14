import io
from types import SimpleNamespace
import pytest

cv2 = pytest.importorskip('cv2')
np = pytest.importorskip('numpy')
Image = pytest.importorskip('PIL.Image')
from level_bridge.ocr import OCRError
from level_bridge.ocr.preprocessing import decode_image, candidates
from level_bridge.ocr.processor import process_image, layout
from level_bridge.ocr.quality import image_warnings


def image_bytes():
    output=io.BytesIO()
    Image.new('RGB',(600,180),'white').save(output,format='PNG')
    return output.getvalue()


@pytest.mark.parametrize('data,name,kwargs', [(b'', 'x.png', {}), (b'bad','x.png',{}),
    (image_bytes(),'x.exe',{}), (image_bytes(),'x.jpg',{}),
    (image_bytes(),'x.png',{'max_bytes':10}), (image_bytes(),'x.png',{'max_pixels':10})])
def test_reject_invalid_images(data,name,kwargs):
    with pytest.raises(OCRError): decode_image(data,name,**kwargs)


def test_low_light_blur_and_orientation():
    assert len(image_warnings(np.zeros((100,100),np.uint8))) == 2
    frame=decode_image(image_bytes(),'x.png')
    engine=SimpleNamespace(image_to_osd=lambda *a,**k: {'rotate':90,'orientation_conf':20})
    options,rotation=candidates(frame,{'deskew':False},engine)
    assert rotation==90 and options[0][1].shape == (600,180)


def test_preserve_layout_and_bbox():
    data={'text':['One','two','Next','Paragraph'], 'conf':[95,54,96,91],
          'left':[1]*4,'top':[2]*4,'width':[10]*4,'height':[5]*4,
          'page_num':[1]*4,'block_num':[1]*4,'par_num':[1,1,1,2],'line_num':[1,1,2,1]}
    text,words=layout(data)
    assert text=='One two\nNext\n\nParagraph'
    assert words[1]['bbox']==[1,2,10,5] and text[words[1]['start']:words[1]['end']]=='two'


def test_empty_page_and_missing_executable(tmp_path):
    path=tmp_path/'page.png';path.write_bytes(image_bytes())
    engine=SimpleNamespace(image_to_data=lambda *a,**k: {'text':[]})
    result=process_image(path,{'orientation':False},engine)
    assert not result['words'] and any('No text' in w for w in result['warnings'])
    def missing(*a,**k): raise FileNotFoundError('tesseract')
    engine.image_to_data=missing
    with pytest.raises(OCRError,match='Install Tesseract'):process_image(path,{'orientation':False},engine)


def test_candidate_quality_selection(tmp_path):
    path=tmp_path/'page.png';path.write_bytes(image_bytes());index=iter([30,94,50])
    def extract(*a,**k):return dict(text=['Science'],conf=[next(index)],left=[0],top=[0],width=[10],height=[10])
    result=process_image(path,{'orientation':False,'deskew':False},SimpleNamespace(image_to_data=extract))
    assert result['candidate']=='contrast' and result['words'][0]['confidence']==94
