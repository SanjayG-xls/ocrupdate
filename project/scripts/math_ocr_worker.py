"""Isolated CPU pix2tex worker. Requires pre-downloaded weights; runtime is offline."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser()
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--image')
    inputs.add_argument('--manifest')
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      TORCH_FORCE_WEIGHTS_ONLY_LOAD='1')
    started=time.perf_counter()
    try:
        import torch
        import pix2tex
        folder=Path(pix2tex.__file__).parent/'model'/'checkpoints'
        if not all((folder/name).is_file() for name in ('weights.pth','image_resizer.pth')):
            raise RuntimeError('Math OCR weights are not installed. Complete the desktop setup first.')
        import requests
        def offline(*a,**k):raise RuntimeError('Network requests are disabled during math OCR.')
        requests.sessions.Session.request=offline
        from pix2tex import cli
        # No clipboard access or automatic model downloads during normal operation.
        cli.clipboard.copy=lambda *a,**k:None
        cli.download_checkpoints=offline
        torch.set_num_threads(min(4,os.cpu_count() or 1))
        torch.manual_seed(42)
        from PIL import Image
        model=cli.LatexOCR()
        loaded=time.perf_counter()
        paths=json.loads(Path(args.manifest).read_text(encoding='utf-8')) if args.manifest else [args.image]
        if not isinstance(paths,list) or not 1<=len(paths)<=40:
            raise ValueError('Math batch must contain 1–40 equation images.')
        predictions=[]
        for path in paths:
            tick=time.perf_counter()
            try:
                with Image.open(path) as image:latex=model(image.convert('RGB'))
                predictions.append(dict(latex=latex,recognition_s=round(time.perf_counter()-tick,3),review_required=True))
            except Exception as exc:
                predictions.append(dict(error=str(exc),review_required=True))
        result=dict(backend='pix2tex (CPU, local)',model_load_s=round(loaded-started,3),
                    recognition_s=round(time.perf_counter()-loaded,3),review_required=True)
        if args.manifest:result['predictions']=predictions
        else:result.update(predictions[0])
    except Exception as exc:
        result={'error':f'{type(exc).__name__}: {exc}'}
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return 1 if 'error' in result else 0


if __name__=='__main__':raise SystemExit(main())
