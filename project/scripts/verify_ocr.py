"""Read-only local dependency/artifact audit and real HTTP UI smoke check.

Run with PYTHONPATH=src python scripts/verify_ocr.py. Does not load a model,
capture a camera, install anything, or send network traffic outside loopback.
"""
import hashlib
import importlib.metadata
import json
import platform
import shutil
import threading
import urllib.request
from pathlib import Path

from level_bridge.config import load_config
from level_bridge.ocr.web import create_app
from werkzeug.serving import make_server


def main():
    cfg=load_config()
    report={'platform':platform.platform(), 'machine':platform.machine(), 'packages':{}, 'artifacts':{},
            'tesseract_executable':shutil.which('tesseract'), 'hardware_tested':False}
    for package in ('Flask','opencv-python-headless','pytesseract','Pillow','executorch'):
        try: report['packages'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:report['packages'][package]='unavailable'
    for filename in ('Qwen2.5-0.5B-Instruct-8da4w-gptq-2k.pte','arm_int8_backup.pte','tokenizer.json'):
        path=cfg.root/'models'/filename
        sha=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
        report['artifacts'][filename]={'bytes':path.stat().st_size,'sha256':sha.hexdigest()}
    server=make_server('127.0.0.1',0,create_app(cfg))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        base=f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(base) as response:
            assert b'Passage Confirmation' in response.read()
            report['http_home_status']=response.status
        with urllib.request.urlopen(base+'/static/scan.js') as response:
            assert b'pendingEdit' in response.read()
            report['http_static_status']=response.status
    finally:
        server.shutdown();worker.join();server.server_close()
    output=cfg.outputs_dir/'ocr_local_audit.json'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
