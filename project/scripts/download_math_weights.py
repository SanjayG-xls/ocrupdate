"""One-time online setup for isolated pix2tex; no images are transmitted."""
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.request


def main():
    spec=importlib.util.find_spec('pix2tex')
    if spec is None:
        raise SystemExit('Install requirements-math-ocr.txt in .venv-math first.')
    folder=Path(spec.origin).parent/'model'/'checkpoints'
    folder.mkdir(parents=True,exist_ok=True)
    records={}
    for name in ('weights.pth','image_resizer.pth'):
        path=folder/name
        url=f'https://github.com/lukas-blecher/LaTeX-OCR/releases/download/v0.0.1/{name}'
        if not path.is_file():
            temporary=path.with_suffix('.download')
            print('Downloading',name,flush=True)
            with urllib.request.urlopen(url,timeout=90) as response,temporary.open('wb') as output:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    output.write(chunk)
            temporary.replace(path)
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        records[name]={'source':url,'bytes':path.stat().st_size,'sha256':sha}
    print(json.dumps(records,indent=2))
    return records


if __name__=='__main__':main()
