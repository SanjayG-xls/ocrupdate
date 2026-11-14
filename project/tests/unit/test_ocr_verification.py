import pytest
from level_bridge.ocr.verification import inspect_text


@pytest.mark.parametrize('expression', ['Speed = Distance × Time', 'Density = Mass * Volume',
    'Pressure = Force + Area', 'Resistance = Voltage * Current', 'Power = Work - Time'])
def test_conflicting_formulas(expression):
    result = inspect_text(expression)
    assert any('CONFLICT' in w for w in result['warnings'])
    assert result['review_required']


def test_supported_and_unsupported_content():
    result = inspect_text('Speed = Distance / Time\nx = √y\n120 km in 2 hours gives 60 km/h; 9 m//s',
                          [{'text':'speec','confidence':54}])
    assert 'matches' in result['formula_candidates'][0]['status']
    assert 'unsupported' in result['formula_candidates'][1]['status']
    assert len(result['numeric_candidates']) == 4
    assert any(u['text']=='km/h' for u in result['unit_candidates'])
    assert 'speec' in result['warnings'][0]


def test_threshold_configurable_no_text_rewrite():
    text = 'Speed = Distance × Time'
    assert not any('Low OCR' in w for w in inspect_text(text,[{'text':'Speed','confidence':54}],50)['warnings'])
    assert inspect_text(text)['formula_candidates'][0]['text'] == text
