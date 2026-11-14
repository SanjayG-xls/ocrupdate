"""Dependency-free checks of transferred models, protected code and OCR settings."""
import hashlib
import json
from pathlib import Path
import re


def sha256(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def main():
    root=Path(__file__).resolve().parent
    project=root/'project'
    protected=json.loads((root/'PROTECTED_OCR_SHA256.json').read_text(encoding='utf-8'))
    models=json.loads((root/'MODEL_MANIFEST.json').read_text(encoding='utf-8'))
    settings=json.loads((root/'FROZEN_OCR_SETTINGS.json').read_text(encoding='utf-8'))
    failures=[]
    for rel,expected in protected.items():
        path=project/rel
        if not path.is_file() or sha256(path)!=expected:failures.append('Protected file changed or missing: '+rel)
    for rel,metadata in models.items():
        path=root/rel
        if not path.is_file() or path.stat().st_size!=metadata['bytes'] or sha256(path)!=metadata['sha256']:
            failures.append('Model/tokenizer changed or missing: '+rel)
    config=(project/'config/config.yaml').read_text(encoding='utf-8')
    start=config.index('\nocr:') if '\nocr:' in config else config.index('ocr:')
    section=config[start:].split('\npaths:',1)[0]
    for key,expected in settings.items():
        if key=='math.enabled':
            match=re.search(r'^  math:\s*\n\s{4}enabled:\s*([^\n#]+)',section,re.M)
        else:match=re.search(r'^  '+re.escape(key)+r':\s*([^\n#]+)',section,re.M)
        if not match or match[1].strip()!=expected:failures.append('Protected OCR setting changed: '+key)
    if failures:
        print('\n'.join(failures));return 1
    print(f'OK: {len(protected)} protected code/test files, {len(models)} model/tokenizer artifacts and {len(settings)} OCR settings verified.')
    print('UI layout and camera/device/path bindings can change within the handoff prompt constraints.')
    print('This verifies file integrity only; it does not load a model or certify Raspberry Pi compatibility.')
    return 0


if __name__=='__main__':raise SystemExit(main())
