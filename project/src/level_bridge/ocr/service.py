"""Local scan records and explicit human verification gate."""
import hashlib
import json
import re
import threading
import uuid
from pathlib import Path

from . import OCRError
from .preprocessing import decode_image
from .processor import process_image
from .verification import inspect_text
from ..passage_processor import process_text, count_words


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class ScanService:
    def __init__(self, cfg, processor=process_image):
        self.cfg, self.processor = cfg, processor
        self.options = cfg.app.get('ocr', {})
        self.root = cfg.path(self.options.get('storage_dir', 'data/ocr')).resolve()
        self.lock = threading.RLock()
        for folder in ('captures', 'processed', 'reviewed'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    def record_path(self, scan_id):
        if not re.fullmatch('[a-f0-9]{32}', scan_id):
            raise OCRError('Invalid scan identifier.')
        return self.root / 'processed' / (scan_id + '.json')

    def read(self, scan_id):
        try:
            return json.loads(self.record_path(scan_id).read_text(encoding='utf-8'))
        except FileNotFoundError as exc:
            raise OCRError('Scan not found.') from exc

    def save(self, record):
        path = self.record_path(record['id'])
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
        return record

    def upload(self, data, filename):
        decode_image(data, filename, self.options.get('max_bytes', 12*1024*1024), self.options.get('max_pixels', 20_000_000))
        scan_id = uuid.uuid4().hex
        path = self.root / 'captures' / (scan_id + Path(filename).suffix.lower())
        with path.open('xb') as stream:
            stream.write(data)
        record = dict(id=scan_id, original_image=str(path), extracted_text='', text='', words=[],
                      confirmed_hash=None, passage_path=None, build=None, warnings=[])
        self.save(record)  # preserve capture even when OCR is missing
        return self.rerun(scan_id)

    def rerun(self, scan_id):
        record = self.read(scan_id)
        record.pop('ocr_error', None)
        try:
            result = self.processor(record['original_image'], self.options)
        except OCRError as exc:
            result = dict(extracted_text='', words=[], warnings=[str(exc)], ocr_duration_s=0,
                          ocr_error=str(exc))
        record.update(result, text=result['extracted_text'], confirmed_hash=None, passage_path=None, build=None)
        return self.save(record)

    def edit(self, scan_id, text):
        record = self.read(scan_id)
        if len(text) > 100_000:
            raise OCRError('Text exceeds the editor size limit. Select a relevant passage.')
        if text != record['text']:
            record.update(text=text, confirmed_hash=None, passage_path=None, build=None)
        record.update(inspect_text(text, record.get('words', []), self.options.get('confidence_threshold', 70)))
        try:
            passage = process_text(text, self.cfg.app['passage'])
            if re.search(r'<\|[^>]*\|>|\[/?INST\]|[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
                raise OCRError('Remove model control tokens or invalid control characters from the passage.')
            record.update(valid=True, word_count=passage.word_count, integrity='Passage requirements met')
            record['warnings'] += passage.warnings
        except ValueError as exc:
            record.update(valid=False, word_count=count_words(text), integrity=str(exc))
        return self.save(record)

    def confirm(self, scan_id, text, checked):
        record = self.edit(scan_id, text)
        if checked is not True or not record['valid']:
            raise OCRError('Validate the passage and select the review checkbox before confirming.')
        path = self.root / 'reviewed' / f'{scan_id}_{uuid.uuid4().hex}.txt'
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
        record.update(confirmed_hash=digest(text), passage_path=str(path))
        return self.save(record)

    def prepare(self, scan_id, backend=None):
        from ..main import _runtime
        from ..pipeline import build
        from ..model_runtime import TemplateRuntime
        from ..lesson_pack import make_pack, write_pack, reseal
        record = self.read(scan_id)
        if record.get('confirmed_hash') != digest(record['text']) or not record.get('passage_path'):
            raise OCRError('Human OCR verification is required before lesson preparation.')
        path = Path(record['passage_path'])
        if digest(path.read_text(encoding='utf-8')) != record['confirmed_hash']:
            raise OCRError('Verified passage changed on disk; confirm again.')
        runtime, info = _runtime(self.cfg, backend, allow_fallback=False)
        art = build(self.cfg, path, runtime)
        templates = build(self.cfg, path, TemplateRuntime()) if runtime.is_llm else art
        pack = make_pack(art, {**info, 'is_llm': runtime.is_llm}, templates)
        pack['payload']['ocr_verification'] = {'scan_id': scan_id, 'text_sha256': record['confirmed_hash']}
        reseal(pack)
        out = self.cfg.path(self.cfg.app['product']['packs_dir']) / f'ocr_{scan_id}_{uuid.uuid4().hex}.lbpack.json'
        write_pack(pack, out)
        attempts = [a for e in art.explanations.values() for a in e.attempts]
        record['build'] = dict(pack_path=str(out), backend=runtime.name,
            model_load_s=info.get('model_load_s'),
            real_inference=bool(runtime.is_llm and any(c.get('ok') and c.get('text') for c in art.generation_calls)),
            accepted_explanations=sum(e.source in ('llm','llm_retry') for e in art.explanations.values()),
            rejected_attempts=sum(not a.generation_ok or not (a.validation or {}).get('passed') for a in attempts),
            template_fallbacks=[k for k,e in art.explanations.items() if e.fallback],
            timings=art.timings, explanations={k:e.to_dict() for k,e in art.explanations.items()},
            teacher_approved=False)
        return self.save(record)

    def delete(self, scan_id):
        record = self.read(scan_id)
        image = Path(record['original_image'])
        if image.parent.resolve() == self.root / 'captures':
            image.unlink(missing_ok=True)
        self.record_path(scan_id).unlink(missing_ok=True)
        # Reviewed passages and lesson packs are deliberately retained.
