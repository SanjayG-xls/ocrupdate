"""Sequence C – passage processing stages."""
import pytest

from level_bridge.passage_processor import PassageError, process_text
from level_bridge.sentence_segmenter import segment


def test_speed_passage_stats(analysed):
    passage, km, registry, _ = analysed
    assert passage.word_count == 177
    assert [s.sid for s in passage.sentences] == [f"S{i}" for i in range(1, 12)]
    assert len(passage.sha256) == 64


def test_segmenter_keeps_decimals_and_abbreviations():
    s = segment("The value is 2.5 m/s, e.g. for a cyclist. Next sentence.")
    assert len(s) == 2 and "2.5" in s[0].text


@pytest.mark.parametrize("text", ["", "Hello there.", "One sentence only with no ending"])
def test_unsupported_passages_rejected(text, cfg):
    with pytest.raises(PassageError):
        process_text(text, cfg.app["passage"])


def test_stage_outputs_are_json_serialisable(analysed):
    import json
    passage, km, registry, _ = analysed
    for obj in (passage.to_dict(), km.to_dict(), registry.to_dict()):
        assert json.loads(json.dumps(obj, default=str))
